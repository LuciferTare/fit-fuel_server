import re
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed as JWTAuthFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import (
    CustomUser,
    GenderChoice,
    Gym,
    Membership,
    MembershipStatus,
    Payment,
    PaymentMode,
    UserStatus,
    UserType,
)
from accounts.utils import MEMBERSHIP_DURATION_MONTHS, calculate_membership_end
from core.serializers import CleansUpReplacedFilesMixin, UploadedFileURLField
from core.utils import delete_if_unreferenced


# ── Shared helpers ────────────────────────────────────────────────────────────

def _run_model_validation(instance):
    """Call model.full_clean() and convert Django ValidationError → DRF."""
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )


def _validate_password_strength(val):
    """Enforce strong-password rules used in serializer fields."""
    errors = []
    if len(val) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", val):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", val):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", val):
        errors.append("Password must contain at least one digit.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~/]', val):
        errors.append("Password must contain at least one special character.")
    if errors:
        raise serializers.ValidationError(errors)
    return val


# ── Auth serializers ──────────────────────────────────────────────────────────

class LoginSerializer(TokenObtainPairSerializer):
    """Phone-number + password login. Returns JWT tokens plus user snapshot."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["user_type"] = user.user_type
        token["status"] = user.status
        return token

    def validate(self, attrs):
        phone = attrs.get(self.username_field)
        password = attrs.get("password")

        try:
            pre_user = CustomUser.objects.get(phone_number=phone)
        except CustomUser.DoesNotExist:
            pre_user = None

        # Verify the password before looking at account status at all, so a
        # wrong password gets the exact same generic response whether or not
        # the phone number is registered, or what state that account is in.
        # Only once the password is confirmed correct do we reveal *why* the
        # account can't log in.
        if pre_user is None or not pre_user.check_password(password):
            raise JWTAuthFailed(
                {
                    "detail": "No active account found with the given credentials",
                    "code": "no_active_account",
                }
            )

        if pre_user.is_deleted or pre_user.status == UserStatus.DELETED:
            raise JWTAuthFailed({"detail": "Account has been deleted.", "code": "account_deleted"})
        if pre_user.status == UserStatus.DISABLED:
            raise JWTAuthFailed({"detail": "Account is disabled.", "code": "account_disabled"})
        if pre_user.status == UserStatus.SUSPENDED:
            raise JWTAuthFailed({"detail": "Account is suspended.", "code": "account_suspended"})
        if pre_user.status != UserStatus.ACTIVE:
            raise JWTAuthFailed({"detail": "Account is not active.", "code": "account_inactive"})

        data = super().validate(attrs)
        user = self.user

        data["user"] = {
            "uuid": str(user.uuid),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "user_type": user.user_type,
            "status": user.status,
            "gym_owner_id": str(user.gym_id) if user.gym_id else None,
            "trainer_id": str(user.trainer_id) if user.trainer_id else None,
        }
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, val):
        user = self.context["request"].user
        if not user.check_password(val):
            raise serializers.ValidationError("Old password is incorrect.")
        return val

    def validate_new_password(self, val):
        return _validate_password_strength(val)

    def validate(self, attrs):
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "New password must differ from old password."}
            )
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


# ── Profile serializers ───────────────────────────────────────────────────────

class UserMeSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    # Named for what it actually holds — the gym OWNER's CustomUser uuid
    # (source="gym_id", the raw FK attname of CustomUser.gym) — not the real
    # Gym master record, which is `gym_uuid` below.
    gym_owner_id = serializers.UUIDField(source="gym_id", read_only=True)
    trainer_id = serializers.UUIDField(read_only=True)
    gym_uuid = serializers.UUIDField(source="gym_details_id", read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_picture",
            "experience_level",
            "user_type",
            "status",
            "gym_owner_id",
            "gym_uuid",
            "trainer_id",
            "created_at",
        ]
        read_only_fields = fields


class ProfileUpdateSerializer(CleansUpReplacedFilesMixin, serializers.ModelSerializer):
    """Writable counterpart to UserMeSerializer for POST /auth/profile/update/."""

    age = serializers.IntegerField(read_only=True)
    gym_owner_id = serializers.UUIDField(source="gym_id", read_only=True)
    trainer_id = serializers.UUIDField(read_only=True)
    gym_uuid = serializers.UUIDField(source="gym_details_id", read_only=True)
    profile_picture = UploadedFileURLField()
    cleanup_file_fields = ("profile_picture",)

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_picture",
            "experience_level",
            "user_type",
            "status",
            "gym_owner_id",
            "gym_uuid",
            "trainer_id",
            "created_at",
        ]
        read_only_fields = [
            "uuid",
            "phone_number",
            "user_type",
            "status",
            "gym_owner_id",
            "gym_uuid",
            "trainer_id",
            "created_at",
        ]


# ── Gym master serializer ───────────────────────────────────────────────────────

class GymSerializer(CleansUpReplacedFilesMixin, serializers.ModelSerializer):
    # Declared explicitly (overriding the model's null=True) so they're
    # required on create/full-update, but still omittable on a partial
    # update — DRF's `partial=True` skips required checks for absent
    # fields, while `allow_null=False` still rejects an explicit `null`,
    # so a partial update can change the location but never clear it.
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, allow_null=False)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, allow_null=False)
    gym_picture = UploadedFileURLField()
    cleanup_file_fields = ("gym_picture",)

    class Meta:
        model = Gym
        fields = ["uuid", "name", "gym_picture", "latitude", "longitude"]
        read_only_fields = ["uuid"]


# ── Gym Owner serializers ─────────────────────────────────────────────────────

class GymOwnerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)
    profile_picture = UploadedFileURLField()
    gym_name = serializers.CharField(write_only=True, max_length=255)
    gym_latitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, write_only=True
    )
    gym_longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, write_only=True
    )
    membership = serializers.ChoiceField(
        choices=list(MEMBERSHIP_DURATION_MONTHS.keys()), write_only=True
    )

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "profile_picture",
            "gym_name",
            "gym_latitude",
            "gym_longitude",
            "membership",
            "status",
            "created_at",
        ]
        read_only_fields = ["uuid", "status", "created_at"]

    def validate_phone_number(self, val):
        if CustomUser.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return val

    def validate_password(self, val):
        return _validate_password_strength(val)

    def create(self, validated_data):
        password = validated_data.pop("password")
        gym_name = validated_data.pop("gym_name")
        gym_latitude = validated_data.pop("gym_latitude")
        gym_longitude = validated_data.pop("gym_longitude")
        membership = validated_data.pop("membership")
        created_by = validated_data.get("created_by")

        with transaction.atomic():
            gym = Gym.objects.create(
                name=gym_name,
                latitude=gym_latitude,
                longitude=gym_longitude,
                created_by=created_by,
                updated_by=created_by,
            )

            start_date = timezone.now().date()
            user = CustomUser(
                **validated_data,
                gym_details=gym,
                membership_start=start_date,
                membership_end=calculate_membership_end(start_date, membership),
                membership_status=MembershipStatus.ACTIVE,
                membership_plan=membership,
            )
            user.set_password(password)
            _run_model_validation(user)
            user.save()
        return user


class GymOwnerDetailSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)
    gym_uuid = serializers.UUIDField(source="gym_details_id", read_only=True)
    trainer_limit = serializers.IntegerField(min_value=0, required=False)
    trainer_count = serializers.IntegerField(read_only=True)
    member_count = serializers.IntegerField(read_only=True)
    profile_picture = UploadedFileURLField()

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_picture",
            "user_type",
            "status",
            "gym_uuid",
            "trainer_limit",
            "trainer_count",
            "member_count",
            "membership_start",
            "membership_end",
            "created_at",
        ]
        read_only_fields = ["uuid", "user_type", "created_at"]

    def update(self, instance, validated_data):
        old_picture = instance.profile_picture.name or None
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        _run_model_validation(instance)
        instance.save()
        new_picture = instance.profile_picture.name or None
        if old_picture and old_picture != new_picture:
            delete_if_unreferenced(old_picture)
        return instance


class TrainerSummarySerializer(serializers.ModelSerializer):
    """Compact trainer representation nested under a gym owner's detail response."""

    name = serializers.CharField(source="get_full_name", read_only=True)
    age = serializers.IntegerField(read_only=True)

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "name",
            "phone_number",
            "date_of_birth",
            "age",
            "gender",
            "created_at",
        ]
        read_only_fields = fields


# ── Trainer serializers ───────────────────────────────────────────────────────

class TrainerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)
    profile_picture = UploadedFileURLField()

    class Meta:
        model = CustomUser
        fields = [
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "profile_picture",
            "experience_level",
        ]

    def validate_phone_number(self, val):
        if CustomUser.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return val

    def validate_password(self, val):
        return _validate_password_strength(val)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = CustomUser(**validated_data)
        user.set_password(password)
        _run_model_validation(user)
        user.save()
        return user


class TrainerDetailSerializer(serializers.ModelSerializer):
    # Named for what it actually holds — the gym OWNER's CustomUser uuid, not
    # the Gym master record's uuid (see UserMeSerializer.gym_uuid for that).
    gym_owner_id = serializers.UUIDField(source="gym_id", read_only=True)
    age = serializers.IntegerField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    profile_picture = UploadedFileURLField()

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_picture",
            "user_type",
            "status",
            "gym_owner_id",
            "password",
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_owner_id", "created_at"]

    def validate_password(self, val):
        return _validate_password_strength(val)

    def update(self, instance, validated_data):
        old_picture = instance.profile_picture.name or None
        password = validated_data.pop("password", None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if password:
            instance.set_password(password)
        _run_model_validation(instance)
        instance.save()
        new_picture = instance.profile_picture.name or None
        if old_picture and old_picture != new_picture:
            delete_if_unreferenced(old_picture)
        return instance


# ── Member serializers ────────────────────────────────────────────────────────

class MemberCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    trainer_uuid = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)
    profile_picture = UploadedFileURLField()

    class Meta:
        model = CustomUser
        fields = [
            "phone_number",
            "password",
            "first_name",
            "last_name",
            "date_of_birth",
            "gender",
            "profile_picture",
            "experience_level",
            "trainer_uuid",
        ]

    def validate_phone_number(self, val):
        if CustomUser.objects.filter(phone_number=val).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return val

    def validate_password(self, val):
        return _validate_password_strength(val)

    def validate(self, attrs):
        trainer_uuid = attrs.pop("trainer_uuid", None)
        if trainer_uuid:
            gym_owner = self.context["request"].user
            try:
                trainer = CustomUser.active_objects.get(
                    uuid=trainer_uuid,
                    user_type=UserType.TRAINER,
                    gym=gym_owner,
                )
            except CustomUser.DoesNotExist:
                raise serializers.ValidationError(
                    {"trainer_uuid": "Trainer not found in this gym."}
                )
            attrs["trainer"] = trainer
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = CustomUser(**validated_data)
        user.set_password(password)
        _run_model_validation(user)
        user.save()
        return user


class MemberDetailSerializer(serializers.ModelSerializer):
    # Named for what it actually holds — the gym OWNER's CustomUser uuid, not
    # the Gym master record's uuid (see UserMeSerializer.gym_uuid for that).
    gym_owner_id = serializers.UUIDField(source="gym_id", read_only=True)
    trainer_id = serializers.UUIDField(allow_null=True, required=False)
    age = serializers.IntegerField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)
    profile_picture = UploadedFileURLField()

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "date_of_birth",
            "age",
            "gender",
            "profile_picture",
            "user_type",
            "status",
            "gym_owner_id",
            "trainer_id",
            "password",
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_owner_id", "created_at"]

    def validate_trainer_id(self, val):
        if val is None:
            return val
        request = self.context.get("request")
        filters = {"uuid": val, "user_type": UserType.TRAINER}
        if request and request.user.user_type == UserType.GYM_OWNER:
            filters["gym"] = request.user
        try:
            CustomUser.active_objects.get(**filters)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Trainer not found in this gym.")
        return val

    def validate_password(self, val):
        return _validate_password_strength(val)

    def update(self, instance, validated_data):
        old_picture = instance.profile_picture.name or None
        password = validated_data.pop("password", None)
        trainer_id = validated_data.pop("trainer_id", ...)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if trainer_id is not ...:
            instance.trainer_id = trainer_id
        if password:
            instance.set_password(password)
        _run_model_validation(instance)
        instance.save()
        new_picture = instance.profile_picture.name or None
        if old_picture and old_picture != new_picture:
            delete_if_unreferenced(old_picture)
        return instance


class MemberProfileSerializer(CleansUpReplacedFilesMixin, serializers.ModelSerializer):
    """Limited self-edit serializer for Members."""

    age = serializers.IntegerField(read_only=True)
    profile_picture = UploadedFileURLField()
    cleanup_file_fields = ("profile_picture",)

    class Meta:
        model = CustomUser
        fields = [
            "uuid",
            "phone_number",
            "first_name",
            "last_name",
            "profile_picture",
            "date_of_birth",
            "age",
            "gender",
            "experience_level",
        ]
        read_only_fields = ["uuid", "phone_number", "date_of_birth", "age"]


class AssignTrainerSerializer(serializers.Serializer):
    trainer_uuid = serializers.UUIDField()


# ── Membership serializers ────────────────────────────────────────────────────

class MembershipSerializer(serializers.ModelSerializer):
    # Explicit (not auto-generated) so soft-deleted members are never a valid
    # choice, regardless of caller — `active_objects`, not the default manager.
    member = serializers.PrimaryKeyRelatedField(
        queryset=CustomUser.active_objects.filter(user_type=UserType.MEMBER)
    )

    class Meta:
        model = Membership
        fields = [
            "uuid",
            "member",
            "start_date",
            "end_date",
            "plan",
            "amount_paid",
            "payment_mode",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "status", "created_at", "updated_at"]

    def validate_member(self, value):
        if value.user_type != UserType.MEMBER:
            raise serializers.ValidationError("User must be of type MEMBER.")
        request = self.context.get("request")
        if (
            request
            and request.user.user_type == UserType.GYM_OWNER
            and value.gym_id != request.user.uuid
        ):
            raise serializers.ValidationError("Member not found in this gym.")
        return value

    def validate(self, attrs):
        start_date = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end_date = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError(
                {"end_date": "end_date must be on or after start_date."}
            )

        # Check for overlapping active memberships (create only)
        if self.instance is None:
            member = attrs.get("member")
            if member and start_date and end_date:
                overlapping = Membership.active_objects.filter(
                    member=member,
                    status=MembershipStatus.ACTIVE,
                    start_date__lte=end_date,
                    end_date__gte=start_date,
                )
                if overlapping.exists():
                    raise serializers.ValidationError(
                        "An active membership already exists overlapping this date range."
                    )

        return attrs

    def create(self, validated_data):
        validated_data.setdefault("status", MembershipStatus.ACTIVE)
        return super().create(validated_data)


# ── Payment serializers ───────────────────────────────────────────────────────

class PaymentListSerializer(serializers.ModelSerializer):
    """Read-only payment shape consumed by the Flutter PaymentModel."""

    member_name = serializers.SerializerMethodField()
    member_phone = serializers.SerializerMethodField()
    gym_name = serializers.SerializerMethodField()
    amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, coerce_to_string=False, read_only=True
    )
    method = serializers.CharField(source="mode", read_only=True)
    membership_plan = serializers.SerializerMethodField()
    payment_date = serializers.DateTimeField(
        source="paid_on", format="%Y-%m-%d", read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            "uuid",
            "invoice_number",
            "member_name",
            "member_phone",
            "gym_name",
            "amount",
            "status",
            "method",
            "membership_plan",
            "payment_date",
            "due_date",
        ]
        read_only_fields = fields

    def get_member_name(self, obj):
        return obj.paid_by.get_full_name() if obj.paid_by else None

    def get_member_phone(self, obj):
        return obj.paid_by.phone_number if obj.paid_by else None

    def get_gym_name(self, obj):
        payer = obj.paid_by
        if not payer:
            return None
        # Gym owner paying the admin — their own gym; member paying — their gym's owner.
        gym_owner = payer if payer.user_type == UserType.GYM_OWNER else payer.gym
        if gym_owner and gym_owner.gym_details:
            return gym_owner.gym_details.name
        return None

    def get_membership_plan(self, obj):
        return obj.membership.plan if obj.membership else None


class PaymentDetailSerializer(PaymentListSerializer):
    """Single-payment detail: everything in the list shape plus linkage and audit fields."""

    member = serializers.UUIDField(source="paid_by.uuid", read_only=True, default=None)
    membership = serializers.UUIDField(
        source="membership.uuid", read_only=True, default=None
    )
    paid_on = serializers.DateTimeField(read_only=True)

    class Meta(PaymentListSerializer.Meta):
        fields = PaymentListSerializer.Meta.fields + [
            "member",
            "membership",
            "paid_on",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ── Phase-3 payment (member-centric) serializers ──────────────────────────────

class MemberPaymentSerializer(serializers.Serializer):
    """Input for POST /api/payments/ — records payment and updates member membership dates."""

    member_id = serializers.UUIDField()
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    mode = serializers.ChoiceField(choices=["cash", "online"])
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    plan = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError({"end_date": "end_date must be on or after start_date."})
        return attrs


class MemberPaymentResponseSerializer(serializers.Serializer):
    """Read-only shape returned after recording a Phase-3 payment."""

    uuid = serializers.UUIDField()
    member_id = serializers.UUIDField(source="member.uuid")
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, source="amount_paid")
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    mode = serializers.CharField(source="payment_mode")
    plan = serializers.CharField()
    status = serializers.CharField()
