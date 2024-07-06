from django.db import transaction
from django.core.cache import cache
from .models import BaseUser, Profile
from config.django import base as settings
import os
import logging
from celery import shared_task
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from datetime import datetime
import redis
import json
import fitz
import re

# Configure the logger
logger = logging.getLogger(__name__)


def create_profile(*, user: BaseUser, bio: str | None) -> Profile:
    """
    Creates a new profile for a given user.

    Args:
        user (BaseUser): The user for whom the profile is being created.
        bio (str | None): An optional bio for the profile.

    Returns:
        Profile: The created profile instance.
    """
    return Profile.objects.create(user=user, bio=bio)


def create_user(*, name: str, email: str, password: str) -> BaseUser:
    """
    Creates a new user with the provided details.

    Args:
        name (str): The name of the user.
        email (str): The email address of the user.
        password (str): The password for the user account.

    Returns:
        BaseUser: The created user instance.
    """
    return BaseUser.objects.create_user(name=name, email=email, password=password)


@transaction.atomic
def register(*, name: str, bio: str | None, email: str, password: str) -> BaseUser:
    """
    Registers a new user and creates a corresponding profile.

    Args:
        name (str): The name of the user.
        bio (str | None): An optional bio for the user's profile.
        email (str): The email address of the user.
        password (str): The password for the user's account.

    Returns:
        BaseUser: The newly created user instance.
    """
    user = create_user(name=name, email=email, password=password)
    create_profile(user=user, bio=bio)

    return user


def profile_count_update():
    """
    Updates the profile count information in the database based on cached data.

    This function iterates over all cached profile data and updates the
    `posts_count`, `subscribers_count`, and `subscriptions_count` for each profile.
    """
    profiles = cache.keys("profile_*")

    for profile_key in profiles:  # e.g., profile_amirbahador.pv@gmail.com
        email = profile_key.replace("profile_", "")
        data = cache.get(profile_key)

        try:
            profile = Profile.objects.get(user__email=email)
            profile.posts_count = data.get("posts_count")
            profile.subscribers_count = data.get("subscribers_count")
            profile.subscriptions_count = data.get("subscriptions_count")
            profile.save()

        except Exception as ex:
            logger.error(f"Error updating profile for {email}: {ex}")


def update_or_add_signature(signature: str, user: BaseUser):
    """
    Updates or adds a signature for the specified user.

    Args:
        signature (str): The path to the signature image.
        user (BaseUser): The user for whom the signature is being updated.
    """
    us = BaseUser.objects.filter(id=user.id).first()

    us.signature = signature
    us.save()


def delete_pdf(user):
    pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
    pdf_path = os.path.join(pdf_dir, f'user_{user.id}.pdf')
    if os.path.exists(pdf_path):
        os.remove(pdf_path)


@shared_task
def generate_user_pdf(user_id: int) -> str:
    """
    Generates a PDF document containing the user's profile information.

    Args:
        user_id (int): The ID of the user for whom the PDF is being generated.

    Returns:
        str: The relative path to the generated PDF.

    Raises:
        Exception: If there is an error during the PDF generation process.
    """
    try:
        user = BaseUser.objects.get(id=user_id)

        # Define the path to save the generated PDF
        pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
        pdf_path = os.path.join(pdf_dir, f'user_{user.id}.pdf')
        # Create a document template and a story
        doc = SimpleDocTemplate(pdf_path, pagesize=letter)
        story = []

        # Get styles
        styles = getSampleStyleSheet()
        title_style = styles['Title']
        normal_style = styles['Normal']

        # Title
        title = Paragraph("User Profile", title_style)
        story.append(title)
        story.append(Spacer(1, 0.5 * inch))

        # Get the current date
        heliacal_date = datetime.now().strftime("%B %d, %Y")

        # Heliacal Date
        heliacal_date_text = f"<b> Date:</b> {heliacal_date}"
        heliacal_date_paragraph = Paragraph(heliacal_date_text, normal_style)
        story.append(heliacal_date_paragraph)
        story.append(Spacer(1, 0.2 * inch))

        # Username
        username_text = f"<b>Username:</b> {user.name}"
        username = Paragraph(username_text, normal_style)
        story.append(username)
        story.append(Spacer(1, 0.2 * inch))

        # Email
        email_text = f"<b>Email:</b> {user.email}"
        email = Paragraph(email_text, normal_style)
        story.append(email)
        story.append(Spacer(1, 0.2 * inch))

        # Profile Image
        if user.signature:
            signature_path = user.signature.path
            img = Image(signature_path, width=2 * inch, height=2 * inch)
            img.hAlign = 'LEFT'
            story.append(img)
            story.append(Spacer(1, 0.2 * inch))
        # Build the PDF
        doc.build(story)

        logger.info(f'PDF generated at: {pdf_path}')
        # Return the relative path to the PDF
        return f"{pdf_path}"
    except Exception as e:
        logger.error(f'Error generating PDF for user {user_id}: {str(e)}')
        raise


def check_task_status(task_id: str, user) -> str:
    """
    Checks the status of a Celery task and returns the result if successful.

    Args:
        task_id (str): The ID of the Celery task.

    Returns:
        str: The path to the generated PDF if the task was successful,
             or a message indicating the task's status.
    """
    redis_client = redis.StrictRedis.from_url(settings.REDIS_URL, decode_responses=True)
    result = json.loads(redis_client.get(f"celery-task-meta-{task_id}"))
    if result.get("status") == "SUCCESS":
        path = result.get("result")
        pdf_document = fitz.open(path)

        page = pdf_document.load_page(0)
        pdf_text = page.get_text()
        print(page.get_images())
        username_pattern = re.compile(r'Username:\s*([\w]+)')
        email_pattern = re.compile(r'Email:\s*([\w\.]+@[\w\.]+)')
        username_match = username_pattern.search(pdf_text).group(1)
        email_match = email_pattern.search(pdf_text).group(1)
        usr = BaseUser.objects.get(id=user)

        if username_match == usr.name and email_match == usr.email and page.get_images():
            pdf_path = result.get("result")
            return f"{pdf_path}"
        else:
            redis_client.set(task_id, 1)
            print(redis_client.get(task_id))
            while int(redis_client.get(task_id)) < 5:
                redis_client.set(task_id, int(redis_client.get(task_id)) + 1)
                generate_user_pdf.delay(user)
            return "something went wrong"
    else:
        redis_client.set(task_id, 1)
        print(redis_client.get(task_id))
        while int(redis_client.get(task_id)) < 5:
            redis_client.set(task_id, int(redis_client.get(task_id)) + 1)
            generate_user_pdf.delay(user)
        return result.get("status")
