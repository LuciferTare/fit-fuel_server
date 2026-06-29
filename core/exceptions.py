from rest_framework.exceptions import APIException


class ConflictException(APIException):
    status_code = 409
    default_detail = "Conflict."
    default_code = "conflict"
