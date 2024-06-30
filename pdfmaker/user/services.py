from django.db import transaction
from django.core.cache import cache
from .models import BaseUser, Profile
import pdfkit
from django.template.loader import render_to_string
from config.django import base as settings
import os
import logging
from celery import shared_task

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
    us = BaseUser.objects.filter(id=user.id)
    us.update(signature=signature)


logger = logging.getLogger(__name__)

@shared_task()
def generate_user_pdf(user_id):
    try:
        user = BaseUser.objects.get(id=user_id)
        # Render the HTML template with user data
        html_content = render_to_string('user_pdf_template.html', {'user': user})

        # Define the path to save the generated PDF
        pdf_dir = os.path.join(settings.MEDIA_ROOT)
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir)
            logger.info(f'Created directory: {pdf_dir}')

        pdf_path = os.path.join(pdf_dir, f'user_{user.id}.pdf')

        # Configure PDFKit with wkhtmltopdf path and options
        pdfkit_config = pdfkit.configuration(wkhtmltopdf=settings.WKHTMLTOPDF_CMD)
        options = {
            'enable-local-file-access': None,  # Allows local file access
            'no-outline': None,  # Remove this option
        }

        pdfkit.from_string(html_content, pdf_path, configuration=pdfkit_config, options=options)

        logger.info(f'PDF generated at: {pdf_path}')
        # Return the relative path to the PDF
        return os.path.join(settings.MEDIA_URL, f'user_{user.id}.pdf')
    except Exception as e:
        logger.error(f'Error generating PDF for user {user_id}: {str(e)}')
        raise