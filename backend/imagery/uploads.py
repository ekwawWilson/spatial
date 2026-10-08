"""Large GeoTIFFs arrive in pieces, so a slow or broken connection doesn't
lose the upload: one request per piece, each well inside the server's time
limit, and the browser carries on from where the server's copy ends.

A piece is accepted only at the exact position the server has reached, so
sending one twice, or after a dropped connection, can't corrupt the file. An
upload belongs to the person and district that started it. Unfinished uploads
are removed by `manage.py clean_media` after a day."""

import fcntl
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import Http404

from transfer.safety import MAX_UPLOAD_BYTES

CHUNK_BYTES = 8 * 1024 * 1024
TIFF_MAGIC = (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+")
_ID = re.compile(r"^[0-9a-f]{32}$")


class Readable(Protocol):
    def read(self, size: int, /) -> bytes: ...


class WrongOffset(Exception):
    """The piece doesn't start where the server's copy ends."""

    def __init__(self, received: int) -> None:
        super().__init__(received)
        self.received = received


def _folder() -> Path:
    return Path(settings.MEDIA_ROOT) / "imagery" / "uploads"


def _part(upload_id: str) -> Path:
    return _folder() / f"{upload_id}.part"


def _meta(upload_id: str) -> Path:
    return _folder() / f"{upload_id}.json"


def check_name(file_name: str) -> str:
    name = Path(file_name).name
    if Path(name).suffix.lower() not in (".tif", ".tiff"):
        raise ValidationError("Upload a GeoTIFF (.tif or .tiff).")
    return name


def start(district_id: int, user_id: int, file_name: str, size: int) -> dict[str, Any]:
    name = check_name(file_name)
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError("Files are limited to 500 MB.")
    upload_id = uuid.uuid4().hex
    _folder().mkdir(parents=True, exist_ok=True)
    _part(upload_id).touch()
    meta = {"district": district_id, "user": user_id, "file_name": name, "size": size}
    _meta(upload_id).write_text(json.dumps({**meta, "started": time.time()}))
    return state(upload_id, meta)


def load(upload_id: str, district_id: int, user_id: int) -> dict[str, Any]:
    """The upload's details, if it is this person's in this district."""
    if not _ID.match(upload_id) or not _meta(upload_id).exists():
        raise Http404
    meta: dict[str, Any] = json.loads(_meta(upload_id).read_text())
    if meta["district"] != district_id or meta["user"] != user_id:
        raise Http404
    return meta


def received(upload_id: str) -> int:
    part = _part(upload_id)
    return part.stat().st_size if part.exists() else 0


def state(upload_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": upload_id,
        "file_name": meta["file_name"],
        "size": meta["size"],
        "received": received(upload_id),
        "chunk_size": CHUNK_BYTES,
    }


def append(upload_id: str, meta: dict[str, Any], offset: int, stream: Readable) -> int:
    """Adds one piece at `offset`; returns how much the server now has."""
    with open(_part(upload_id), "ab") as fh:
        # One piece at a time per upload (a retry may overlap the original).
        fcntl.flock(fh, fcntl.LOCK_EX)
        have = fh.seek(0, 2)
        if offset != have:
            raise WrongOffset(have)
        data = stream.read(CHUNK_BYTES + 1)
        if len(data) > CHUNK_BYTES:
            raise ValidationError(f"Pieces are limited to {CHUNK_BYTES // (1024 * 1024)} MB.")
        if have + len(data) > meta["size"]:
            raise ValidationError("More bytes than the file's declared size.")
        fh.write(data)
        return have + len(data)


def take(upload_id: str, meta: dict[str, Any], target: Path) -> None:
    """Moves the finished file to `target`."""
    have = received(upload_id)
    if have != meta["size"]:
        raise ValidationError(f"The upload isn't complete ({have} of {meta['size']} bytes).")
    with open(_part(upload_id), "rb") as fh:
        if fh.read(4) not in TIFF_MAGIC:
            discard(upload_id)
            raise ValidationError("The file isn't a GeoTIFF.")
    target.parent.mkdir(parents=True, exist_ok=True)
    _part(upload_id).replace(target)
    _meta(upload_id).unlink(missing_ok=True)


def discard(upload_id: str) -> None:
    _part(upload_id).unlink(missing_ok=True)
    _meta(upload_id).unlink(missing_ok=True)
