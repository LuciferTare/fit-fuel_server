import re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed as JWTAuthFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import (
    CustomUser,
    GenderChoice,
    Membership,
    MembershipStatus,
    Payment,
    PaymentMode,
    UserStatus,
    UserType,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _run_model_validation(instance):
    """Call model.full_clean() and convert Django ValidationError → DRF."""
    try:
        instance.full_clean()
    except DjangoValidationError as exc:
        raise serializers.ValidationError(
            exc.message_dict if hasattr(exc, "message_dict") else exc.messages
        )


def _validate_password_strength(value):
    """Enforce strong-password rules used in serializer fields."""
    errors = []
    if len(value) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", value):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", value):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", value):
        errors.append("Password must contain at least one digit.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>\-_=+\[\]\\;\'`~/]', value):
        errors.append("Password must contain at least one special character.")
    if errors:
        raise serializers.ValidationError(errors)
    return value


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
        try:
            pre_user = CustomUser.objects.get(phone_number=phone)
            if pre_user.is_deleted or pre_user.status == UserStatus.DELETED:
                raise JWTAuthFailed({"detail": "Account has been deleted.", "code": "account_deleted"})
            if pre_user.status == UserStatus.DISABLED:
                raise JWTAuthFailed({"detail": "Account is disabled.", "code": "account_disabled"})
            if pre_user.status == UserStatus.SUSPENDED:
                raise JWTAuthFailed({"detail": "Account is suspended.", "code": "account_suspended"})
            if pre_user.status != UserStatus.ACTIVE:
                raise JWTAuthFailed({"detail": "Account is not active.", "code": "account_inactive"})
        except CustomUser.DoesNotExist:
            pass

        data = super().validate(attrs)
        user = self.user

        data["user"] = {
            "uuid": str(user.uuid),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "user_type": user.user_type,
            "status": user.status,
            "gym_id": str(user.gym_id) if user.gym_id else None,
            "trainer_id": str(user.trainer_id) if user.trainer_id else None,
        }
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def validate_new_password(self, value):
        return _validate_password_strength(value)

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
    gym_id = serializers.UUIDField(read_only=True)
    trainer_id = serializers.UUIDField(read_only=True)

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
            "gym_id",
            "trainer_id",
            "created_at",
        ]
        read_only_fields = fields


# ── Gym Owner serializers ─────────────────────────────────────────────────────

class GymOwnerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)

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
        ]

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate_password(self, value):
        return _validate_password_strength(value)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = CustomUser(**validated_data)
        user.set_password(password)
        _run_model_validation(user)
        user.save()
        return user


class GymOwnerDetailSerializer(serializers.ModelSerializer):
    age = serializers.IntegerField(read_only=True)

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
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "created_at"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        _run_model_validation(instance)
        instance.save()
        return instance


# ── Trainer serializers ───────────────────────────────────────────────────────

class TrainerCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)

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
        ]

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate_password(self, value):
        return _validate_password_strength(value)

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = CustomUser(**validated_data)
        user.set_password(password)
        _run_model_validation(user)
        user.save()
        return user


class TrainerDetailSerializer(serializers.ModelSerializer):
    gym_id = serializers.UUIDField(read_only=True)
    age = serializers.IntegerField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

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
            "gym_id",
            "password",
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_id", "created_at"]

    def validate_password(self, value):
        return _validate_password_strength(value)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        _run_model_validation(instance)
        instance.save()
        return instance


# ── Member serializers ────────────────────────────────────────────────────────

class MemberCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    trainer_uuid = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    first_name = serializers.CharField(required=True)
    last_name = serializers.CharField(required=True)
    gender = serializers.ChoiceField(choices=GenderChoice.choices, required=True)

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
            "trainer_uuid",
        ]

    def validate_phone_number(self, value):
        if CustomUser.objects.filter(phone_number=value).exists():
            raise serializers.ValidationError("This phone number is already registered.")
        return value

    def validate_password(self, value):
        return _validate_password_strength(value)

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
    gym_id = serializers.UUIDField(read_only=True)
    trainer_id = serializers.UUIDField(allow_null=True, required=False)
    age = serializers.IntegerField(read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

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
            "gym_id",
            "trainer_id",
            "password",
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_id", "created_at"]

    def validate_trainer_id(self, value):
        if value is None:
            return value
        request = self.context.get("request")
        filters = {"uuid": value, "user_type": UserType.TRAINER}
        if request and request.user.user_type == UserType.GYM_OWNER:
            filters["gym"] = request.user
        try:
            CustomUser.active_objects.get(**filters)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError("Trainer not found in this gym.")
        return value

    def validate_password(self, value):
        return _validate_password_strength(value)

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        trainer_id = validated_data.pop("trainer_id", ...)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if trainer_id is not ...:
            instance.trainer_id = trainer_id
        if password:
            instance.set_password(password)
        _run_model_validation(instance)
        instance.save()
        return instance


class MemberProfileSerializer(serializers.ModelSerializer):
    """Limited self-edit serializer for Members."""

    age = serializers.IntegerField(read_only=True)

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
        ]
        read_only_fields = ["uuid", "phone_number", "date_of_birth", "age"]


class AssignTrainerSerializer(serializers.Serializer):
    trainer_uuid = serializers.UUIDField()


# ── Membership serializers ────────────────────────────────────────────────────

class MembershipSerializer(serializers.ModelSerializer):
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

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "uuid",
            "membership",
            "amount",
            "mode",
            "paid_on",
            "created_at",
        ]
        read_only_fields = ["uuid", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_membership(self, value):
        request = self.context.get("request")
        if request and request.user.user_type == UserType.GYM_OWNER:
            if value.member.gym != request.user:
                raise serializers.ValidationError(
                    "Membership does not belong to your gym."
                )
        return value


# ── Phase-3 payment (member-centric) serializers ──────────────────────────────

class MemberPaymentSerializer(serializers.Serializer):
    """Input for POST /api/payments/ — records payment and updates member membership dates."""

    member_id = serializers.UUIDField()
    date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    mode = serializers.ChoiceField(choices=["Cash", "Online"])
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
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    date = serializers.DateField(source="start_date")
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    mode = serializers.CharField(source="payment_mode")
    plan = serializers.CharField()
    status = serializers.CharField()
