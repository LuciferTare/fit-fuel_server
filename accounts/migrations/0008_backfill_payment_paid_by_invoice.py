from django.db import migrations
from django.utils import timezone


def backfill_payments(apps, schema_editor):
    Payment = apps.get_model("accounts", "Payment")
    for payment in Payment.objects.select_related("membership").all():
        update_fields = []
        if payment.paid_by_id is None and payment.membership_id:
            payment.paid_by_id = payment.membership.member_id
            update_fields.append("paid_by")
        if not payment.invoice_number:
            payment.invoice_number = (
                f"INV-{timezone.now():%Y%m%d}-{payment.uuid.hex[:6].upper()}"
            )
            update_fields.append("invoice_number")
        if update_fields:
            payment.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_payment_due_date_payment_invoice_number_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_payments, migrations.RunPython.noop),
    ]
