"""Shared check-in rules — used by both the live check-in/out endpoints
(attendance/views.py) and the attendance backup-sync path (backup/views.py),
so the two can't drift apart on what's allowed.
"""
from accounts.models import UserType
from attendance.models import Attendance
from core.utils import haversine_distance_m

# Check-in/out must be within this many meters of the user's gym.
ATTENDANCE_RADIUS_M = 50


def user_gym_location(user):
    """(latitude, longitude) of the Gym `user`'s account belongs to, or
    None if the user isn't linked to a gym or that gym has no location set."""
    gym_owner = user.gym
    if gym_owner is None or gym_owner.gym_details is None:
        return None
    gym = gym_owner.gym_details
    if gym.latitude is None or gym.longitude is None:
        return None
    return gym.latitude, gym.longitude


def geofence_error(user, lat, lng):
    """Plain-text reason `lat`/`lng` is rejected for `user`'s gym, or None if
    it's within ATTENDANCE_RADIUS_M of the gym location. Applies identically
    to members and trainers."""
    location = user_gym_location(user)
    if location is None:
        return "Your gym has no registered location. Contact your gym owner."
    distance = haversine_distance_m(lat, lng, *location)
    if distance > ATTENDANCE_RADIUS_M:
        return (
            f"You are {distance:.0f}m away from your gym — check-in/out "
            f"must be within {ATTENDANCE_RADIUS_M}m of the gym location."
        )
    return None


def photo_required_error(user, photo):
    """A trainer's check-in/out must include a photo; a member's never does."""
    if user.user_type == UserType.TRAINER and not photo:
        return "A photo is required."
    return None


def duplicate_checkin_error(user, check_in_date):
    """Trainers: any still-open (not checked-out) record blocks a new
    check-in. Members: at most one check-in per calendar day."""
    if user.user_type == UserType.TRAINER:
        if Attendance.active_objects.filter(user=user, check_out__isnull=True).exists():
            return "You're already checked in."
    else:
        if Attendance.active_objects.filter(user=user, check_in__date=check_in_date).exists():
            return "You've already checked in today."
    return None
