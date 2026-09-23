from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User


def password_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.WEB_APP_URL}/reset-password?uid={uid}&token={token}"


def send_password_reset(user: User) -> None:
    send_mail(
        "Reset your password",
        "Someone asked to reset the password for your Spatial Planning Platform account.\n\n"
        f"To choose a new password, open:\n{password_link(user)}\n\n"
        "If this wasn't you, ignore this email; your password won't change.",
        None,
        [user.email],
    )


def send_invitation(user: User, district_name: str, invited_by: User) -> None:
    send_mail(
        f"You've been added to {district_name}",
        f"{invited_by.get_full_name() or invited_by.email} has given you access to "
        f"{district_name} on the Spatial Planning Platform.\n\n"
        f"To set your password and sign in, open:\n{password_link(user)}\n",
        None,
        [user.email],
    )
