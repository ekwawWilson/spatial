"""Whether the current request may see restricted (personal) attribute values.

Set by the authenticator for each request and cleared when the request ends.
Outside a request (background jobs, commands) nothing is hidden: those run
on behalf of the platform, and what they produce is gated by its own
permission (exports, project files).
"""

from contextvars import ContextVar

_allowed: ContextVar[bool] = ContextVar("sensitive_allowed", default=True)


def set_allowed(value: bool) -> None:
    _allowed.set(value)


def allowed() -> bool:
    return _allowed.get()
