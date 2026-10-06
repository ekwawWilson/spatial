"""Field photos, uploaded in chunks so a broken connection can carry on where
it stopped. A chunk is accepted only at the exact position the server has
reached, so sending one twice, or out of order, can't corrupt the file. The
file is accepted as complete only when its SHA-256 matches what the device
declared."""

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Photo

MAX_PHOTO_BYTES = 25 * 1024 * 1024
MAX_CHUNK_BYTES = 2 * 1024 * 1024


class WrongOffset(Exception):
    """The chunk doesn't start where the server's copy ends."""


def photo_path(photo: Photo) -> Path:
    return (
        Path(settings.MEDIA_ROOT) / "sync" / "photos" / str(photo.district_id) / f"{photo.uuid}.jpg"
    )


def _part(photo: Photo) -> Path:
    path = photo_path(photo)
    return path.with_suffix(".part")


def received_bytes(photo: Photo) -> int:
    """What is really on disk (the database count can be ahead of it if a
    request died between writing and saving)."""
    if photo.complete:
        return photo.size
    part = _part(photo)
    return part.stat().st_size if part.exists() else 0


def append_chunk(photo: Photo, offset: int, data: bytes) -> Photo:
    if photo.complete:
        return photo
    have = received_bytes(photo)
    if offset != have:
        raise WrongOffset(have)
    if len(data) > MAX_CHUNK_BYTES:
        raise ValidationError(f"Chunks are limited to {MAX_CHUNK_BYTES // (1024 * 1024)} MB.")
    if have + len(data) > photo.size:
        raise ValidationError("More bytes than the declared size of the photo.")
    part = _part(photo)
    part.parent.mkdir(parents=True, exist_ok=True)
    with open(part, "ab") as fh:
        fh.write(data)
    photo.received = have + len(data)
    if photo.received == photo.size:
        digest = hashlib.sha256()
        with open(part, "rb") as fh:
            for block in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != photo.sha256.lower():
            part.unlink()
            photo.received = 0
            photo.save(update_fields=["received"])
            raise ValidationError(
                "The photo arrived damaged (its checksum doesn't match)."
                " Send it again from the start."
            )
        part.replace(photo_path(photo))
        photo.complete = True
        photo.path = str(photo_path(photo).relative_to(settings.MEDIA_ROOT))
    photo.save(update_fields=["received", "complete", "path"])
    return photo
