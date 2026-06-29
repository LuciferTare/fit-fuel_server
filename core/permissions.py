from rest_framework import permissions


class IsAuthenticatedUser(permissions.IsAuthenticated):
    message = "You do not have access to this resource."


class HavePermissions(permissions.DjangoModelPermissions):
    message = "You do not have access to this resource."


def _get_user_type():
    from accounts.models import UserType
    return UserType


class IsAdmin(permissions.BasePermission):
    message = "Admin access required."

    def has_permission(self, request, view):
        UserType = _get_user_type()
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.user_type == UserType.ADMIN
        )


class IsGymOwner(permissions.BasePermission):
    message = "Gym Owner access required."

    def has_permission(self, request, view):
        UserType = _get_user_type()
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.user_type == UserType.GYM_OWNER
        )


class IsTrainer(permissions.BasePermission):
    message = "Trainer access required."

    def has_permission(self, request, view):
        UserType = _get_user_type()
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.user_type == UserType.TRAINER
        )


class IsMember(permissions.BasePermission):
    message = "Member access required."

    def has_permission(self, request, view):
        UserType = _get_user_type()
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.user_type == UserType.MEMBER
        )


class IsAdminOrGymOwner(permissions.BasePermission):
    message = "Admin or Gym Owner access required."

    def has_permission(self, request, view):
        UserType = _get_user_type()
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.user_type in (UserType.ADMIN, UserType.GYM_OWNER)
        )
