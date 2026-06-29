import re

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed as JWTAuthFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from accounts.models import CustomUser, GenderChoice, UserStatus, UserType


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
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_id", "created_at"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
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
    trainer_id = serializers.UUIDField(read_only=True)
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
            "gym_id",
            "trainer_id",
            "created_at",
        ]
        read_only_fields = ["uuid", "phone_number", "user_type", "gym_id", "created_at"]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
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
