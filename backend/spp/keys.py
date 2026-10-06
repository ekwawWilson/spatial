"""Organisation keys for .spp files.

SPP_ORG_KEYS holds "key_id:base64key" pairs separated by commas. The first is
used for new files; the others are kept so older files still open (rotation).
Keys live only in the server's secrets and are never sent to any client; every
deployment that must open the same files needs the same keys.
"""

import base64
import binascii
import hashlib
import re
import secrets
from dataclasses import dataclass

from django.conf import settings

KEY_BYTES = 32  # AES-256
KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")


class KeyError_(Exception):
    """A problem with the configured organisation keys (message is for users)."""


class NoKeysConfigured(KeyError_):
    def __init__(self) -> None:
        super().__init__(
            "This server has no organisation key for .spp files yet."
            " A system administrator must set SPP_ORG_KEYS (see docs/ops/spp-keys.md)."
        )


class UnknownKey(KeyError_):
    def __init__(self, key_id: str) -> None:
        self.key_id = key_id
        super().__init__(
            f"This file is protected with the organisation key '{key_id}', which this server"
            " doesn't have. It can only be opened on a server that holds that key."
        )


@dataclass(frozen=True)
class OrgKey:
    key_id: str
    secret: bytes

    @property
    def fingerprint(self) -> str:
        """Safe to show: lets administrators check two servers hold the same key."""
        return hashlib.sha256(b"spp-key-fingerprint|" + self.secret).hexdigest()[:16]


def parse(text: str) -> list[OrgKey]:
    """Keys from the SPP_ORG_KEYS format; raises KeyError_ on a malformed value
    (without echoing key material)."""
    keys: list[OrgKey] = []
    for position, part in enumerate((p.strip() for p in text.split(",")), start=1):
        if not part:
            continue
        key_id, sep, encoded = part.partition(":")
        if not sep or not KEY_ID.match(key_id):
            raise KeyError_(
                f"SPP_ORG_KEYS entry {position}: expected key_id:base64key, with an id of"
                " letters, digits, '.', '_' or '-'."
            )
        try:
            secret = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise KeyError_(f"SPP_ORG_KEYS entry {position} ({key_id}): not valid base64.") from exc
        if len(secret) != KEY_BYTES:
            raise KeyError_(
                f"SPP_ORG_KEYS entry {position} ({key_id}): the key must be {KEY_BYTES} bytes."
            )
        if any(k.key_id == key_id for k in keys):
            raise KeyError_(f"SPP_ORG_KEYS has two keys called '{key_id}'.")
        keys.append(OrgKey(key_id, secret))
    return keys


def ring() -> list[OrgKey]:
    return parse(settings.SPP_ORG_KEYS)


def active() -> OrgKey:
    """The key new files are protected with."""
    keys = ring()
    if not keys:
        raise NoKeysConfigured()
    return keys[0]


def get(key_id: str) -> OrgKey:
    keys = ring()
    if not keys:
        raise NoKeysConfigured()
    for key in keys:
        if key.key_id == key_id:
            return key
    raise UnknownKey(key_id)


def generate(key_id: str) -> str:
    """A new random key as an SPP_ORG_KEYS entry."""
    if not KEY_ID.match(key_id):
        raise KeyError_("Key ids use letters, digits, '.', '_' or '-' (at most 40 characters).")
    return f"{key_id}:{base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode()}"
