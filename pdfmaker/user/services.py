from django.db import transaction
from django.core.cache import cache
from .models import BaseUser, Profile
from config.django import base as settings
import os
import logging
from celery import shared_task
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from datetime import datetime
import redis
from django.http import JsonResponse
import json


def create_profile(*, user: BaseUser, bio: str | None) -> Profile:
    return Profile.objects.create(user=user, bio=bio)


def create_user(*, name, email: str, password: str) -> BaseUser:
    return BaseUser.objects.create_user(name=name, email=email, password=password)


@transaction.atomic
def register(*, name, bio: str | None, email: str, password: str) -> BaseUser:
    user = create_user(name=name, email=email, password=password)
    create_profile(user=user, bio=bio)

    return user


def profile_count_update():
    profiles = cache.keys("profile_*")

    for profile_key in profiles:  # profile_amirbahador.pv@gmail.com
        email = profile_key.replace("profile_", "")
        data = cache.get(profile_key)

        try:
            profile = Profile.objects.get(user__email=email)
            profile.posts_count = data.get("posts_count")
            profile.subscribers_count = data.get("subscribers_count")
            profile.subscriptions_count = data.get("subscriptions_count")
            profile.save()

        except Exception as ex:
            print(ex)


def update_or_add_signature(signature, user):
    us = BaseUser.objects.filter(id=user.id).first()

    us.signature = signature
    us.save()


logger = logging.getLogger(__name__)


@shared_task()
def generate_user_pdf(user_id):
    try:
        user = BaseUser.objects.get(id=user_id)

        # Define the path to save the generated PDF
        pdf_dir = os.path.join(settings.MEDIA_ROOT, "pdfs")
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)
            logger.info(f'Created directory: {pdf_dir}')

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
        return pdf_path
    except Exception as e:
        logger.error(f'Error generating PDF for user {user_id}: {str(e)}')
        raise


def check_task_status(task_id):
    redis_client = redis.StrictRedis.from_url(settings.REDIS_URL, decode_responses=True)
    result = json.loads(redis_client.get(f"celery-task-meta-{task_id}"))
    if result.get("status") == "SUCCESS":
        pdf_path = result.get("result")
        return pdf_path
    result = result.get("status")
    message = f"task was{result}"
    return message

