from math import atan2, cos, radians, sin, sqrt

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

EARTH_RADIUS_M = 6371000


def haversine_distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in meters between two lat/lng points."""
    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return EARTH_RADIUS_M * 2 * atan2(sqrt(a), sqrt(1 - a))


def mail_letter_sender(mail_subject, to_email, template, context):
    try:
        html_message = render_to_string(template, context)
        email = EmailMultiAlternatives(mail_subject, mail_subject, to=[to_email])
        email.attach_alternative(html_message, "text/html")
        email.send()
    except Exception as e:
        print(e)
