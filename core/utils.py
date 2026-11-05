from math import atan2, cos, radians, sin, sqrt

from django.core.files.storage import default_storage
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

EARTH_RADIUS_M = 6371000


def _file_bearing_fields():
    """(model, field_name) pairs for every model field an uploaded file
    (via `UploadedFileURLField`/`POST /api/upload-file/`, or a plain
    `FileField` fed the same way) can end up in. Used to check whether a
    storage path is still referenced by *any* row before deleting it.

    Deliberately excludes: music's `thumb_ref`/`asset_ref`/`icon_ref`/
    `cover_ref` (bundled app-asset path strings, not real storage paths —
    never write these to `default_storage`), and `Attendance.check_in_photo`/
    `check_out_photo` (write-once, no update path ever replaces them, so
    there's nothing to garbage-collect there).

    Imported lazily to avoid a module-import-time dependency from `core`
    (loaded early) on `accounts`/`music` (loaded later).
    """
    from accounts.models import CustomUser, Gym
    from music.models import Playlist, Song

    return (
        (CustomUser, "profile_picture"),
        (Gym, "gym_picture"),
        (Song, "thumb_file"),
        (Song, "asset_file"),
        (Playlist, "icon_file"),
        (Playlist, "cover_file"),
    )


def delete_if_unreferenced(old_path):
    """Deletes `old_path` from storage, but only if no row of any known
    file-bearing model/field still references it.

    Call this only for a path that has *already* been replaced — i.e. after
    the row that used to hold it has been saved with its new value — so
    that row no longer counts against the check and doesn't need to be
    excluded explicitly.
    """
    if not old_path:
        return
    for model, field_name in _file_bearing_fields():
        if model.objects.filter(**{field_name: old_path}).exists():
            return
    if default_storage.exists(old_path):
        default_storage.delete(old_path)


def haversine_distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in meters between two lat/lng points."""
    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlng / 2) ** 2
    return EARTH_RADIUS_M * 2 * atan2(sqrt(a), sqrt(1 - a))


def mail_letter_sender(mail_subject, to_email, template, context):
    try:
        html_message = render_to_string(template, context)
        email = EmailMultiAlternatives(mail_subject, mail_subject, to=[to_email])
        email.attach_alternative(html_message, "text/html")
        email.send()
    except Exception as e:
        print(e)
