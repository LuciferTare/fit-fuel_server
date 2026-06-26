import ipaddress

from django.contrib.gis.geoip2 import GeoIP2
from django.http import HttpRequest, HttpResponse
from django.views.decorators.http import require_http_methods
from drf_spectacular.utils import extend_schema
from ipware import get_client_ip
from rest_framework import status, viewsets
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    renderer_classes,
)
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from user_agents import parse as parse_ua

from core import renderers


class NoAuthAPIView(GenericAPIView):
    authentication_classes = []
    permission_classes = []
    renderer_classes = (renderers.ResponseRenderer,)


class BaseAPIView(GenericAPIView):
    renderer_classes = (renderers.ResponseRenderer,)


class BaseModelViewSet(viewsets.ModelViewSet):
    renderer_classes = (renderers.ResponseRenderer,)


class NoAuthNoPermMixin:
    authentication_classes = []
    permission_classes = []


@extend_schema(summary="Ping Server", tags=["Utils"])
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def ping(request: HttpRequest):
    return Response("pong", status=status.HTTP_200_OK)


@require_http_methods(["HEAD"])
def health_check(request: HttpRequest):
    return HttpResponse(status=status.HTTP_200_OK)


@extend_schema(summary="IP Check", tags=["Utils"])
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
@renderer_classes([renderers.JSONRenderer])
def my_ip(request: HttpRequest):
    try:
        if "ip" in request.GET:
            ip = request.GET.get("ip")
            is_routable = ipaddress.ip_address(ip).is_global
        else:
            ip, is_routable = get_client_ip(request)

        if not is_routable:
            return Response(
                {"detail": f"IP {ip} is private or not routable."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        geo = GeoIP2()
        location_data = {}
        try:
            location_data = geo.city(ip)
        except Exception:
            return Response(
                {"ip": ip, "detail": "Location not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        ua_string = request.META.get("HTTP_USER_AGENT", "")
        user_agent = parse_ua(ua_string)

        response = {
            "ip": ip,
            "location": {
                "country": location_data.get("country_name"),
                "city": location_data.get("city"),
                "region": location_data.get("region"),
                "latitude": location_data.get("latitude"),
                "longitude": location_data.get("longitude"),
            },
            "browser": {
                "name": user_agent.browser.family,
                "version": user_agent.browser.version_string,
            },
            "os": {
                "name": user_agent.os.family,
                "version": user_agent.os.version_string,
            },
            "device": {
                "type": (
                    "mobile"
                    if user_agent.is_mobile
                    else (
                        "tablet"
                        if user_agent.is_tablet
                        else "pc" if user_agent.is_pc else "unknown"
                    )
                ),
                "brand": user_agent.device.brand,
                "model": user_agent.device.model,
            },
            "is_bot": user_agent.is_bot,
        }
        return Response(response, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"detail": f"Unable to get IP location: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST,
        )
