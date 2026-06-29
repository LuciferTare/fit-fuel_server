"""
Notification helpers.

The backend does NOT send messages directly. Instead it:
  - Renders a template into a plain-text message string (for SMS).
  - Builds a wa.me deep-link URL the client opens to send a WhatsApp message.

The caller (management command, viewset action, etc.) receives the rendered
text / URL and passes it to the frontend or logs it.
"""
import logging
from urllib.parse import quote

from .templates import TEMPLATES

logger = logging.getLogger(__name__)


def render_message(template_name: str, context: dict) -> str:
    """Return a notification string with all {placeholders} filled in."""
    template = TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"Unknown notification template: {template_name!r}")
    try:
        return template.format(**context)
    except KeyError as exc:
        raise ValueError(
            f"Template '{template_name}' is missing context key {exc}"
        ) from exc


def build_whatsapp_url(phone_number: str, message: str) -> str:
    """Return a wa.me URL that opens WhatsApp with the message pre-filled.

    Args:
        phone_number: International format with or without leading '+'.
                      E.g. '+917700900000' or '917700900000'.
        message:      Plain-text message body.

    Returns:
        URL string — e.g. 'https://wa.me/917700900000?text=Hi%20...'
    """
    clean = phone_number.strip().lstrip("+").replace(" ", "").replace("-", "")
    return f"https://wa.me/{clean}?text={quote(message)}"


def get_whatsapp_url(phone_number: str, template_name: str, context: dict) -> str:
    """Render *template_name* and return a ready-to-open WhatsApp deep-link."""
    message = render_message(template_name, context)
    url = build_whatsapp_url(phone_number, message)
    logger.info("WhatsApp link built — to=%s template=%s", phone_number, template_name)
    return url


def get_sms_text(template_name: str, context: dict) -> str:
    """Render *template_name* and return the plain-text SMS body."""
    text = render_message(template_name, context)
    logger.info("SMS text rendered — template=%s", template_name)
    return text
