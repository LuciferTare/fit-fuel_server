from django import forms
from django.contrib import admin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.utils.html import format_html

from accounts.models import CustomUser, Membership, Payment


class CustomUserCreationForm(forms.ModelForm):
    """Used in the Django admin 'Add user' page."""

    password1 = forms.CharField(label="Password", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Password confirmation", widget=forms.PasswordInput)

    class Meta:
        model = CustomUser
        fields = ("phone_number", "user_type", "status")

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1")
        p2 = self.cleaned_data.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("Passwords do not match.")
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class CustomUserChangeForm(forms.ModelForm):
    """Used in the Django admin 'Change user' page."""

    password = ReadOnlyPasswordHashField(
        label="Password",
        help_text=(
            "Raw passwords are not stored. You can change the password via "
            '<a href="../password/">this form</a>.'
        ),
    )

    class Meta:
        model = CustomUser
        fields = "__all__"


@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    list_display = [
        "phone_number",
        "first_name",
        "last_name",
        "user_type",
        "status",
        "gym",
        "trainer",
        "is_active",
        "created_at",
    ]
    list_filter = ["user_type", "status", "is_active", "is_staff", "gender"]
    search_fields = ["phone_number", "first_name", "last_name"]
    ordering = ["-created_at"]
    filter_horizontal = ["groups", "user_permissions"]
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "profile_picture_preview",
        "age",
    ]

    fieldsets = (
        (None, {"fields": ("phone_number", "password")}),
        (
            "Personal Info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "date_of_birth",
                    "age",
                    "gender",
                    "profile_picture",
                    "profile_picture_preview",
                )
            },
        ),
        ("Business", {"fields": ("user_type", "status", "gym", "trainer")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "uuid",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "is_deleted",
                    "deleted_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "phone_number",
                    "password1",
                    "password2",
                    "first_name",
                    "last_name",
                    "user_type",
                    "status",
                    "gym",
                    "trainer",
                ),
            },
        ),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        defaults = {}
        if obj is None:
            defaults["form"] = self.add_form
            defaults["fields"] = forms.ALL_FIELDS
        defaults.update(kwargs)
        return super().get_form(request, obj, **defaults)

    def profile_picture_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" width="80" height="80" style="object-fit:cover;border-radius:50%;" />',
                obj.profile_picture.url,
            )
        return "No photo"

    profile_picture_preview.short_description = "Photo Preview"


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ["uuid", "member", "plan", "start_date", "end_date", "amount_paid", "payment_mode", "status", "created_at"]
    list_filter = ["status", "payment_mode"]
    search_fields = ["member__phone_number", "member__first_name", "member__last_name", "plan"]
    ordering = ["-created_at"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by", "updated_by", "deleted_at"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["uuid", "membership", "amount", "mode", "paid_on", "created_at"]
    list_filter = ["mode"]
    search_fields = ["membership__member__phone_number", "membership__member__first_name"]
    ordering = ["-paid_on"]
    readonly_fields = ["uuid", "created_at", "updated_at", "created_by", "updated_by", "deleted_at"]
