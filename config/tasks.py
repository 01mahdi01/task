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


@shared_task
def generate_user_pdf(user_id):
    # Fetch the user information
    user = BaseUser.objects.get(id=user_id)
    print(40*"*")

    # Render the HTML template with user data
    # html_content = render_to_string('/pdfmaker/templates/user_pdf_template.html', {'user': user})
    template_path = '/pdfmaker/templates/user_pdf_template.html'
    with open(template_path, 'r') as template_file:
        template_content = template_file.read()
    template = Template(template_content)
    # Path to save the generated PDF

    context = Context({'user': user})
    html_content = template.render(context)
    pdf_path = f'/pdfmaker/user/pdfs/user_{user.id}.pdf'  # Adjust the path as needed

    # Generate the PDF
    pdfkit.from_string(html_content, pdf_path, configuration=pdfkit.configuration(wkhtmltopdf=base.WKHTMLTOPDF_CMD))

    return pdf_path