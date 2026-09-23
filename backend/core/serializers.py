from typing import Any

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import AuditLog, District, Membership, Region, Role, User
from .permissions import permissions_for_role


class RegionSerializer(serializers.ModelSerializer[Region]):
    class Meta:
        model = Region
        fields = ["id", "name", "code"]


class DistrictSerializer(serializers.ModelSerializer[District]):
    region_name = serializers.CharField(source="region.name", read_only=True)

    class Meta:
        model = District
        fields = ["id", "name", "code", "kind", "region", "region_name", "is_active"]


class DistrictBriefSerializer(serializers.ModelSerializer[District]):
    class Meta:
        model = District
        fields = ["id", "name", "code"]


class MyMembershipSerializer(serializers.ModelSerializer[Membership]):
    district = DistrictBriefSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ["district", "role", "permissions"]

    def get_permissions(self, obj: Membership) -> list[str]:
        return permissions_for_role(obj.role)


class MeSerializer(serializers.ModelSerializer[User]):
    memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_system_admin", "memberships"]

    def get_memberships(self, obj: User) -> list[dict[str, Any]]:
        active = obj.memberships.filter(is_active=True, district__is_active=True).select_related(
            "district"
        )
        return MyMembershipSerializer(active, many=True).data  # type: ignore[return-value]


class LoginSerializer(serializers.Serializer[None]):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class LoginResponseSerializer(serializers.Serializer[None]):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = MeSerializer()


class RefreshTokenSerializer(serializers.Serializer[None]):
    refresh = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer[None]):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer[None]):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer[None]):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        validate_password(value, user=self.context["request"].user)
        return value


class UserSerializer(serializers.ModelSerializer[User]):
    is_locked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_system_admin",
            "is_locked",
            "last_login",
            "date_joined",
        ]
        read_only_fields = ["last_login", "date_joined"]

    def get_is_locked(self, obj: User) -> bool:
        from django.utils import timezone

        return bool(obj.locked_until and obj.locked_until > timezone.now())


class MemberUserSerializer(serializers.ModelSerializer[User]):
    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "is_active"]


class MembershipSerializer(serializers.ModelSerializer[Membership]):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user", "role", "is_active", "created_at"]
        read_only_fields = ["created_at"]


class MembershipCreateSerializer(serializers.Serializer[None]):
    """Adds a person to the current district. Creates (and invites) the user
    if no account exists for the email yet."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices)
    first_name = serializers.CharField(required=False, allow_blank=True, max_length=150)
    last_name = serializers.CharField(required=False, allow_blank=True, max_length=150)


class AuditLogSerializer(serializers.ModelSerializer[AuditLog]):
    changed_fields = serializers.ListField(child=serializers.CharField(), read_only=True)
    user_email = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "occurred_at",
            "table_name",
            "row_id",
            "action",
            "changed_fields",
            "before",
            "after",
            "user_id",
            "user_email",
            "district_id",
        ]

    def get_user_email(self, obj: AuditLog) -> str | None:
        if not obj.user_id:
            return None
        # List views pass a pre-fetched id -> email map to avoid a query per row.
        emails: dict[int, str] | None = self.context.get("user_emails")
        if emails is not None:
            return emails.get(obj.user_id)
        return User.objects.filter(id=obj.user_id).values_list("email", flat=True).first()
