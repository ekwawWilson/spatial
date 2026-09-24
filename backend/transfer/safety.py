"""Safe handling of uploaded archives: size limits, zip-bomb and path checks."""

import zipfile
from pathlib import Path, PurePosixPath

from django.core.exceptions import ValidationError

MAX_UPLOAD_BYTES = 500 * 1024 * 1024
MAX_UNZIPPED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 10_000
MAX_COMPRESSION_RATIO = 200


def check_zip(path: Path) -> list[str]:
    """Member names of a zip, after refusing anything unsafe: absolute paths or
    '..' (path traversal), too many members, or a suspicious total/ratio (zip bomb)."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValidationError("The file is not a valid zip archive.") from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_MEMBERS:
            raise ValidationError(f"The archive has more than {MAX_ZIP_MEMBERS} files.")
        total = 0
        names = []
        for info in infos:
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
                raise ValidationError(f"Unsafe path in archive: {info.filename}")
            total += info.file_size
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ValidationError(
                    "The archive's compression ratio is suspicious (possible zip bomb)."
                )
            if not info.is_dir():
                names.append(info.filename)
        if total > MAX_UNZIPPED_BYTES:
            raise ValidationError("The archive unpacks to more than 2 GB.")
    return names
