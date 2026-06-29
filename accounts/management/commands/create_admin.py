from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser, UserStatus, UserType


class Command(BaseCommand):
    help = "Create a Platform Admin user"

    def add_arguments(self, parser):
        parser.add_argument("--phone", required=True, help="Admin phone number")
        parser.add_argument("--password", required=True, help="Admin password")
        parser.add_argument("--first-name", default="Admin", help="First name")
        parser.add_argument("--last-name", default="", help="Last name")

    def handle(self, *args, **options):
        phone = options["phone"]
        password = options["password"]
        first_name = options["first_name"]
        last_name = options["last_name"]

        if CustomUser.objects.filter(phone_number=phone).exists():
            raise CommandError(f"A user with phone number '{phone}' already exists.")

        user = CustomUser.objects.create_superuser(
            phone_number=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            user_type=UserType.ADMIN,
            status=UserStatus.ACTIVE,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Platform Admin created successfully: {user.phone_number}"
            )
        )
