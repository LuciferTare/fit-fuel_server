from django.db import migrations, models


class Migration(migrations.Migration):
    """Add membership snapshot fields to CustomUser and gym+type composite index."""

    dependencies = [
        ("accounts", "0002_customuser_trainer_limit_membership_payment"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="membership_start",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="membership_end",
            field=models.DateField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="customuser",
            name="membership_status",
            field=models.CharField(
                blank=True,
                choices=[("ACTIVE", "Active"), ("EXPIRED", "Expired")],
                max_length=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="membership_plan",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddIndex(
            model_name="customuser",
            index=models.Index(fields=["gym", "user_type"], name="user_gym_type_idx"),
        ),
    ]
