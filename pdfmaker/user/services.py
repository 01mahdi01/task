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

from django.template import Template, Context


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
        # if not os.path.exists(pdf_dir):
        #     os.makedirs(pdf_dir)
        #     logger.info(f'Created directory: {pdf_dir}')

        pdf_path = os.path.join(pdf_dir, f'user_{user.id}.pdf')

        # Create a canvas object
        c = canvas.Canvas(pdf_path, pagesize=letter)

        # Set title
        c.setTitle("User Profile")

        # Draw the username
        c.setFont("Helvetica-Bold", 12)
        c.drawString(100, 750, "Username:")
        c.setFont("Helvetica", 12)
        c.drawString(200, 750, user.name)

        # Draw the email
        c.setFont("Helvetica-Bold", 12)
        c.drawString(100, 730, "Email:")
        c.setFont("Helvetica", 12)
        c.drawString(200, 730, user.email)

        # Draw the profile image if it exists
        if user.signature:
            # signature_path = os.path.join(settings.MEDIA_ROOT, "signatures", user.signature.url)  # Correctly resolve the image path
            signature_path = user.signature.path
            c.drawImage(signature_path, 100, 600, width=2 * inch, height=2 * inch)

        # Save the PDF file
        c.save()

        logger.info(f'PDF generated at: {pdf_path}')
        # Return the relative path to the PDF
        return pdf_path
    except Exception as e:
        logger.error(f'Error generating PDF for user {user_id}: {str(e)}')
        raise
