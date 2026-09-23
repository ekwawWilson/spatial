from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .health import run_checks


class HealthView(APIView):
    """Liveness/readiness probe used by docker-compose, CI and the web app."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses={200: OpenApiTypes.OBJECT, 503: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        results = run_checks()
        return Response(results, status=200 if results["ok"] else 503)
