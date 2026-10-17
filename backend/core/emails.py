# ruff: noqa: E501 - the HTML of an email reads better unbroken
"""The platform's emails: a plain-text body (what tests and old mail readers
use) and the same message as branded HTML, in the style of the DVLA system's."""

import logging
from html import escape

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .models import User

log = logging.getLogger(__name__)

GREEN = "#1f6f4a"
GOLD = "#FCD116"


def password_link(user: User) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.WEB_APP_URL}/reset-password?uid={uid}&token={token}"


def _name(user: User) -> str:
    return user.get_full_name() or user.email


def layout(name: str, body: str) -> str:
    """The branded email every message uses. `body` is trusted HTML."""
    return f"""
      <div style="font-family:sans-serif;max-width:480px;margin:0 auto;padding:24px">
        <div style="background:{GREEN};padding:20px 24px;border-radius:6px 6px 0 0">
          <p style="color:{GOLD};font-size:11px;font-weight:700;letter-spacing:2px;margin:0">REPUBLIC OF GHANA</p>
          <p style="color:#fff;font-size:18px;font-weight:900;margin:4px 0 0">Spatial Planning Platform</p>
        </div>
        <div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 6px 6px;padding:28px 24px">
          <p style="color:#374151;margin:0 0 16px">Hello <strong>{escape(name)}</strong>,</p>
          {body}
          <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
          <p style="color:#6b7280;font-size:11px;margin:0">
            Community planning for Metropolitan, Municipal and District Assemblies &bull; Authorised personnel only
          </p>
        </div>
      </div>
    """


def button(url: str, label: str) -> str:
    return f"""
          <p style="text-align:center;margin:0 0 24px">
            <a href="{escape(url)}" style="background:{GREEN};color:#fff;text-decoration:none;font-weight:700;padding:12px 24px;border-radius:6px;display:inline-block">{escape(label)}</a>
          </p>
          <p style="color:#6b7280;font-size:12px;margin:0 0 16px;word-break:break-all">
            Or copy this link into your browser:<br>{escape(url)}
          </p>"""


def send(user: User, subject: str, text: str, html: str) -> None:
    message = EmailMultiAlternatives(subject, text, None, [user.email])
    message.attach_alternative(layout(_name(user), html), "text/html")
    try:
        message.send()
    except Exception:
        # The mail server can't be reached: the person is still added, and the
        # message (with its link) goes to the log for an administrator to pass on.
        log.exception("Email to %s not sent", user.email)
        log.warning("Unsent email to %s: %s\n%s", user.email, subject, text)


def send_password_reset(user: User) -> None:
    link = password_link(user)
    send(
        user,
        "Reset your password",
        "Someone asked to reset the password for your Spatial Planning Platform account.\n\n"
        f"To choose a new password, open:\n{link}\n\n"
        "If this wasn't you, ignore this email; your password won't change.",
        f"""<p style="color:#374151;margin:0 0 24px">
            Someone asked to reset the password for your Spatial Planning Platform account.
            Choose a new password here:
          </p>
          {button(link, "Choose a new password")}
          <p style="color:#6b7280;font-size:13px;margin:0">
            If this wasn't you, ignore this email: your password won't change.
          </p>""",
    )


def send_invitation(user: User, district_name: str, invited_by: User) -> None:
    by = _name(invited_by)
    link = password_link(user)
    send(
        user,
        f"You've been added to {district_name}",
        f"{by} has given you access to {district_name} on the Spatial Planning Platform.\n\n"
        f"To set your password and sign in, open:\n{link}\n",
        f"""<p style="color:#374151;margin:0 0 24px">
            <strong>{escape(by)}</strong> has given you access to <strong>{escape(district_name)}</strong>
            on the Spatial Planning Platform. Set your password to sign in:
          </p>
          {button(link, "Set my password")}
          <p style="color:#6b7280;font-size:13px;margin:0">
            The link works once. If you weren't expecting this, you can ignore it.
          </p>""",
    )
