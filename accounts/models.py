import uuid as uuid_lib

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.managers import ActiveUserManager, UserManager
from core.models import BaseModel


class UserType(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    GYM_OWNER = "GYM_OWNER", "Gym Owner"
    TRAINER = "TRAINER", "Trainer"
    MEMBER = "MEMBER", "Member"


class UserStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"
    SUSPENDED = "SUSPENDED", "Suspended"
    DELETED = "DELETED", "Deleted"


class GenderChoice(models.TextChoices):
    MALE = "MALE", "Male"
    FEMALE = "FEMALE", "Female"
    OTHER = "OTHER", "Other"


# ── Gym master ──────────────────────────────────────────────────────────────────

class Gym(BaseModel):
    """Master record for a gym's name, referenced by its owner's CustomUser via `gym_details`."""

    name = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Gym"
        verbose_name_plural = "Gyms"
        db_table = "gyms"

    def __str__(self):
        return self.name


class CustomUser(AbstractBaseUser, PermissionsMixin):
    # Primary key
    uuid = models.UUIDField(primary_key=True, default=uuid_lib.uuid4, editable=False)

    # Identity
    phone_number = models.CharField(max_length=15, unique=True)

    # Profile
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, choices=GenderChoice.choices, blank=True)
    profile_picture = models.ImageField(
        upload_to="profile_pictures/", null=True, blank=True
    )

    # Business
    user_type = models.CharField(
        max_length=20, choices=UserType.choices, default=UserType.MEMBER, db_index=True
    )
    trainer_limit = models.IntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        db_index=True,
    )

    # Relationships — gym points to a GYM_OWNER user, trainer points to a TRAINER user
    gym = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="gym_users",
        limit_choices_to={"user_type": UserType.GYM_OWNER},
    )
    trainer = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trainer_members",
        limit_choices_to={"user_type": UserType.TRAINER},
    )
    # Set only for GYM_OWNER users — points to the master Gym record holding their gym's name.
    gym_details = models.ForeignKey(
        Gym,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="owners",
    )

    # Membership tracking (denormalised for fast reads / reports)
    membership_start = models.DateField(null=True, blank=True)
    membership_end = models.DateField(null=True, blank=True, db_index=True)
    membership_status = models.CharField(
        max_length=10,
        choices=[("ACTIVE", "Active"), ("EXPIRED", "Expired")],
        null=True,
        blank=True,
    )
    membership_plan = models.CharField(max_length=100, null=True, blank=True)

    # Django flags
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Audit
    created_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_users",
        editable=False,
    )
    updated_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_users",
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    objects = UserManager()
    active_objects = ActiveUserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        db_table = "users"
        indexes = [
            models.Index(fields=["gym", "user_type"], name="user_gym_type_idx"),
        ]

    def __str__(self):
        return f"{self.get_full_name()} ({self.phone_number})"

    def get_full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.phone_number

    def get_short_name(self):
        return self.first_name or self.phone_number

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = timezone.now().date()
        dob = self.date_of_birth
        return (
            today.year
            - dob.year
            - ((today.month, today.day) < (dob.month, dob.day))
        )

    def soft_delete(self, deleted_by=None):
        self.is_deleted = True
        self.status = UserStatus.DELETED
        self.deleted_at = timezone.now()
        if deleted_by:
            self.updated_by = deleted_by
        self.save(
            update_fields=[
                "is_deleted",
                "status",
                "deleted_at",
                "updated_by",
                "updated_at",
            ]
        )

    def clean(self):
        super().clean()
        self._validate_relationships()

    def _validate_relationships(self):
        if self.user_type == UserType.ADMIN:
            if self.gym_id or self.trainer_id or self.gym_details_id:
                raise ValidationError("Admin cannot have gym, trainer, or gym-profile assignment.")
        elif self.user_type == UserType.GYM_OWNER:
            if self.trainer_id:
                raise ValidationError("Gym Owner cannot have a trainer assignment.")
            if self.gym_id:
                raise ValidationError("Gym Owner cannot belong to another gym.")
        elif self.user_type == UserType.TRAINER:
            if self.trainer_id:
                raise ValidationError("Trainer cannot reference another trainer.")
            if self.gym_details_id:
                raise ValidationError("Trainer cannot have a gym-profile assignment.")
        elif self.user_type == UserType.MEMBER:
            if self.gym_details_id:
                raise ValidationError("Member cannot have a gym-profile assignment.")
            if self.trainer_id and self.gym_id:
                trainer = CustomUser.objects.filter(uuid=self.trainer_id).first()
                if trainer and trainer.gym_id != self.gym_id:
                    raise ValidationError(
                        "Trainer must belong to the same gym as the member."
                    )


# ── Membership & Payment enums ─────────────────────────────────────────────────

class MembershipStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    EXPIRED = "EXPIRED", "Expired"


class PaymentMode(models.TextChoices):
    CASH = "CASH", "Cash"
    ONLINE = "ONLINE", "Online"


# ── Membership model ───────────────────────────────────────────────────────────

class Membership(BaseModel):
    member = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="memberships",
        limit_choices_to={"user_type": UserType.MEMBER},
    )
    start_date = models.DateField()
    end_date = models.DateField()
    plan = models.CharField(max_length=100, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PaymentMode.choices)
    status = models.CharField(
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        verbose_name = "Membership"
        verbose_name_plural = "Memberships"
        db_table = "memberships"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.member} — {self.plan or 'Custom'} ({self.start_date} to {self.end_date})"


# ── Payment model ──────────────────────────────────────────────────────────────

class Payment(BaseModel):
    membership = models.ForeignKey(
        Membership,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    mode = models.CharField(max_length=10, choices=PaymentMode.choices)
    paid_on = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        db_table = "payments"
        ordering = ["-paid_on"]

    def __str__(self):
        return f"Payment {self.uuid} — {self.amount} ({self.mode})"
