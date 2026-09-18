from urllib.parse import urlparse
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import default_storage
from rest_framework import serializers

UPLOAD_DIR = "uploads"
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024


class FileUploadSerializer(serializers.Serializer):
    """Backs POST /api/upload-file/ — validates an image upload and stores
    it under MEDIA_ROOT/uploads/, returning the storage-relative path."""

    file = serializers.ImageField()

    def validate_file(self, value):
        ext = value.name.rsplit(".", 1)[-1].lower() if "." in value.name else ""
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_IMAGE_EXTENSIONS))}."
            )
        if value.size > MAX_UPLOAD_SIZE_BYTES:
            raise serializers.ValidationError("File too large — max 5MB.")
        return value

    def save(self):
        file = self.validated_data["file"]
        ext = file.name.rsplit(".", 1)[-1].lower()
        filename = f"{uuid4().hex}.{ext}"
        return default_storage.save(f"{UPLOAD_DIR}/{filename}", file)


class UploadedFileURLField(serializers.ImageField):
    """Like ImageField for reads (renders the stored file's absolute URL via
    the inherited ``to_representation``), but for writes accepts the URL
    string returned by POST /api/upload-file/ (or any URL already pointing
    at a file under MEDIA_ROOT) instead of a raw multipart file, resolving
    it to the storage-relative path that gets assigned onto the model's
    ImageField/FileField. This is what lets an unchanged value round-trip
    on save instead of failing DRF's file-only validation.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str) or not data:
            raise serializers.ValidationError(
                "Expected the URL returned by POST /api/upload-file/, not a raw file."
            )
        path = urlparse(data).path
        if not path.startswith(settings.MEDIA_URL):
            raise serializers.ValidationError(
                "Must be a URL returned by POST /api/upload-file/."
            )
        relative_path = path[len(settings.MEDIA_URL):]
        if not default_storage.exists(relative_path):
            raise serializers.ValidationError("Uploaded file not found.")
        return relative_path
