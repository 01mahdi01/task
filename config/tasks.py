from time import sleep
from celery import shared_task
from pdfmaker.user.models import BaseUser
from django.template.loader import render_to_string
import pdfkit
from config.django import base
from django.template import Template, Context

@shared_task
def notify_customers(message):
    print(message)
    sleep(10)


