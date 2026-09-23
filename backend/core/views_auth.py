from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .auth import attempt_login
from .emails import send_password_reset
from .models import User
from .permissions import request_user
from .serializers import (
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RefreshTokenSerializer,
)
from .tenancy import set_db_context

# Same message whether the email is unknown, the password wrong or the account
# locked, so responses don't reveal which accounts exist.
LOGIN_FAILED = "Email or password is incorrect, or the account is temporarily locked."


def revoke_refresh_tokens(user: User) -> None:
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


class LoginView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 401: OpenApiResponse(description=LOGIN_FAILED)},
    )
    def post(self, request: Request) -> Response:
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = attempt_login(request, data.validated_data["email"], data.validated_data["password"])
        if user is None:
            # Return, don't raise: raising would roll back the failure count.
            return Response({"detail": LOGIN_FAILED}, status=status.HTTP_401_UNAUTHORIZED)
        set_db_context(user_id=user.id, district_id=None, is_system_admin=user.is_system_admin)
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": MeSerializer(user).data,
            }
        )


class LogoutView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RefreshTokenSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = RefreshTokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            RefreshToken(data.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise serializers.ValidationError({"refresh": str(exc)}) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(request_user(request)).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = ChangePasswordSerializer(data=request.data, context={"request": request})
        data.is_valid(raise_exception=True)
        user = request_user(request)
        if not user.check_password(data.validated_data["current_password"]):
            raise serializers.ValidationError({"current_password": "Incorrect password."})
        user.set_password(data.validated_data["new_password"])
        user.save(update_fields=["password"])
        revoke_refresh_tokens(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetRequestSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = PasswordResetRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user:
            send_password_reset(user)
        # Same response either way, so this can't be used to discover accounts.
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = PasswordResetConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        invalid = serializers.ValidationError({"token": "This link is invalid or has expired."})
        try:
            pk = int(force_str(urlsafe_base64_decode(data.validated_data["uid"])))
        except (TypeError, ValueError, OverflowError):
            raise invalid from None
        user = User.objects.filter(pk=pk, is_active=True).first()
        if not user or not default_token_generator.check_token(user, data.validated_data["token"]):
            raise invalid
        try:
            validate_password(data.validated_data["new_password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)}) from exc
        user.set_password(data.validated_data["new_password"])
        user.failed_login_count = 0
        user.locked_until = None
        user.save(update_fields=["password", "failed_login_count", "locked_until"])
        revoke_refresh_tokens(user)
        return Response(status=status.HTTP_204_NO_CONTENT)
