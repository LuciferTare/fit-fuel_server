from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string


def mail_letter_sender(mail_subject, to_email, template, context):
    try:
        html_message = render_to_string(template, context)
        email = EmailMultiAlternatives(mail_subject, mail_subject, to=[to_email])
        email.attach_alternative(html_message, "text/html")
        email.send()
    except Exception as e:
        print(e)
