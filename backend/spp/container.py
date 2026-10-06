"""The .spp container: an encrypted, authenticated wrapper around the package.

Layout (big-endian):

    magic        8 bytes   b"\\x89SPP\\r\\n\\x1a\\n"
    version      u16       container version (1)
    header_len   u32
    header       JSON      key id, wrapped data key, nonces, chunk size, file id
    chunks       repeated  u32 length + AES-256-GCM ciphertext (with its tag)

Each file gets a random 256-bit data key, wrapped with the organisation key
(AES-256-GCM). The package is encrypted in chunks so large projects stream
through bounded memory. Every chunk's nonce carries its index and whether it
is the last, and every chunk authenticates the header, so changing, removing,
reordering or truncating anything is detected. Nothing in the file is
readable without the organisation key except the key's id.
"""

import base64
import hashlib
import json
import secrets
import struct
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import keys

MAGIC = b"\x89SPP\r\n\x1a\n"
CONTAINER_VERSION = 1
CHUNK_SIZE = 1024 * 1024
MAX_HEADER = 64 * 1024
TAG = 16
WRAP_AAD = b"spp-key-wrap|"


class SppError(Exception):
    """The file can't be opened (message is for users)."""


class NotAnSppFile(SppError):
    def __init__(self) -> None:
        super().__init__("This isn't a .spp project file.")


class NewerVersion(SppError):
    def __init__(self) -> None:
        super().__init__(
            "This file was made by a newer version of the platform. Update this server to open it."
        )


class Damaged(SppError):
    def __init__(self) -> None:
        super().__init__(
            "The file is damaged or has been altered, so it was refused. Use an unmodified copy."
        )


class WrongKey(SppError):
    def __init__(self, key_id: str) -> None:
        super().__init__(
            f"The file's key couldn't be unlocked. This server's organisation key '{key_id}'"
            " isn't the one the file was made with, or the file has been altered."
        )


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _nonce(prefix: bytes, index: int, last: bool) -> bytes:
    return prefix + struct.pack(">IB", index, 1 if last else 0)


def encrypt(source: Path, target: Path) -> dict[str, Any]:
    """Writes `source` (the package) to `target` as a .spp file. Returns the
    header (file id, key id), which holds nothing secret."""
    org = keys.active()
    data_key = AESGCM.generate_key(bit_length=256)
    wrap_nonce = secrets.token_bytes(12)
    header = {
        "file_id": str(uuid.uuid4()),
        "key_id": org.key_id,
        "wrap_nonce": _b64(wrap_nonce),
        "wrapped_key": _b64(
            AESGCM(org.secret).encrypt(wrap_nonce, data_key, WRAP_AAD + org.key_id.encode())
        ),
        "nonce_prefix": _b64(secrets.token_bytes(7)),
        "chunk_size": CHUNK_SIZE,
    }
    header_bytes = json.dumps(header, sort_keys=True).encode()
    preamble = MAGIC + struct.pack(">HI", CONTAINER_VERSION, len(header_bytes)) + header_bytes
    aad = hashlib.sha256(preamble).digest()
    cipher = AESGCM(data_key)
    prefix = base64.b64decode(header["nonce_prefix"])
    with open(source, "rb") as src, open(target, "wb") as out:
        out.write(preamble)
        index = 0
        chunk = src.read(CHUNK_SIZE)
        while True:
            following = src.read(CHUNK_SIZE)
            last = not following
            sealed = cipher.encrypt(_nonce(prefix, index, last), chunk, aad)
            out.write(struct.pack(">I", len(sealed)) + sealed)
            if last:
                break
            chunk, index = following, index + 1
    return header


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    data = stream.read(size)
    if len(data) != size:
        raise Damaged()
    return data


def read_header(stream: BinaryIO) -> tuple[dict[str, Any], bytes]:
    """The header and the value every chunk authenticates."""
    start = stream.read(len(MAGIC) + 6)
    if len(start) < len(MAGIC) + 6 or not start.startswith(MAGIC):
        raise NotAnSppFile()
    version, header_len = struct.unpack(">HI", start[len(MAGIC) :])
    if version > CONTAINER_VERSION:
        raise NewerVersion()
    if version < 1 or header_len > MAX_HEADER:
        raise Damaged()
    header_bytes = _read_exact(stream, header_len)
    try:
        header = json.loads(header_bytes)
        for name in ("key_id", "wrap_nonce", "wrapped_key", "nonce_prefix", "chunk_size"):
            header[name]
        if not isinstance(header["key_id"], str) or not isinstance(header["chunk_size"], int):
            raise TypeError
    except (ValueError, KeyError, TypeError) as exc:
        raise Damaged() from exc
    return header, hashlib.sha256(start + header_bytes).digest()


def decrypt(source: Path, target: Path) -> dict[str, Any]:
    """Writes the package inside `source` to `target`. Raises SppError (or a
    keys error) with a message for the user when it can't."""
    with open(source, "rb") as src:
        header, aad = read_header(src)
        org = keys.get(header["key_id"])  # UnknownKey explains itself
        try:
            data_key = AESGCM(org.secret).decrypt(
                base64.b64decode(header["wrap_nonce"]),
                base64.b64decode(header["wrapped_key"]),
                WRAP_AAD + org.key_id.encode(),
            )
        except InvalidTag as exc:
            # Same key id but a different key (another organisation's), or an altered header.
            raise WrongKey(org.key_id) from exc
        except ValueError as exc:
            raise Damaged() from exc
        try:
            prefix = base64.b64decode(header["nonce_prefix"])
        except ValueError as exc:
            raise Damaged() from exc
        if len(prefix) != 7 or not 0 < header["chunk_size"] <= 64 * CHUNK_SIZE:
            raise Damaged()
        cipher = AESGCM(data_key)
        limit = header["chunk_size"] + TAG
        with open(target, "wb") as out:
            index = 0
            size_bytes = _read_exact(src, 4)
            while True:
                (size,) = struct.unpack(">I", size_bytes)
                if size < TAG or size > limit:
                    raise Damaged()
                sealed = _read_exact(src, size)
                size_bytes = src.read(4)
                last = not size_bytes
                if not last and len(size_bytes) != 4:
                    raise Damaged()
                try:
                    out.write(cipher.decrypt(_nonce(prefix, index, last), sealed, aad))
                except InvalidTag as exc:
                    raise Damaged() from exc
                if last:
                    break
                index += 1
    return header
