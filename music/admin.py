from django.contrib import admin
from django.utils.html import format_html

from music.models import Playlist, PlaylistSong, Song


def _thumb_preview(file_field, ref):
    src = file_field.url if file_field else ref
    if src:
        return format_html(
            '<img src="{}" width="60" height="60" style="object-fit:cover;border-radius:6px;" />',
            src,
        )
    return "—"


@admin.register(Song)
class SongAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "artist", "duration", "is_remote", "created_at"]
    list_filter = ["is_remote", "is_deleted"]
    search_fields = ["title", "artist"]
    ordering = ["id"]
    readonly_fields = ["created_at", "updated_at", "created_by", "deleted_at", "thumb_preview"]

    def thumb_preview(self, obj):
        return _thumb_preview(obj.thumb_file, obj.thumb_ref)

    thumb_preview.short_description = "Thumb Preview"


class PlaylistSongInline(admin.TabularInline):
    model = PlaylistSong
    extra = 0
    autocomplete_fields = ["song"]
    ordering = ["position"]


@admin.register(Playlist)
class PlaylistAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "color", "is_remote", "created_at"]
    list_filter = ["is_remote", "is_deleted"]
    search_fields = ["title"]
    ordering = ["id"]
    inlines = [PlaylistSongInline]
    readonly_fields = [
        "created_at",
        "updated_at",
        "created_by",
        "deleted_at",
        "icon_preview",
        "cover_preview",
    ]

    def icon_preview(self, obj):
        return _thumb_preview(obj.icon_file, obj.icon_ref)

    icon_preview.short_description = "Icon Preview"

    def cover_preview(self, obj):
        return _thumb_preview(obj.cover_file, obj.cover_ref)

    cover_preview.short_description = "Cover Preview"
