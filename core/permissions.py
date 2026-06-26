from rest_framework import permissions


class IsAuthenticatedUser(permissions.IsAuthenticated):
    message = "You do not have access to this resource."


class HavePermissions(permissions.DjangoModelPermissions):
    message = "You do not have access to this resource."
