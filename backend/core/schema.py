"""OpenAPI (drf-spectacular) extensions. Imported in CoreConfig.ready()."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter


class TenantJWTScheme(SimpleJWTScheme):  # type: ignore[no-untyped-call]
    target_class = "core.auth.TenantJWTAuthentication"
    name = "jwtAuth"


DISTRICT_HEADER = OpenApiParameter(
    "X-District-ID",
    OpenApiTypes.INT,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Id of the district the request acts in (see /api/auth/me/ memberships).",
)
