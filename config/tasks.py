from time import sleep
from celery import shared_task
from config.django import base
from django.template import Template, Context

@shared_task
def notify_customers(message):
    print(message)
    sleep(10)


