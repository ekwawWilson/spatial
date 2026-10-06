"""Organisation keys for .spp files: make one, or list the ones installed.

    manage.py spp_key generate [--id 2026-10] [--write-env /path/to/.env]
    manage.py spp_key list

`generate` prints a new SPP_ORG_KEYS entry. With --write-env it also installs
it in that env file as the first (active) key, keeping the existing keys so
older files still open. Restart the backend and worker afterwards.
"""

import re
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from spp import keys

LINE = re.compile(r"^SPP_ORG_KEYS=(.*)$", re.M)


def install(env_file: Path, entry: str) -> list[str]:
    """Puts `entry` first in the file's SPP_ORG_KEYS; returns all key ids, new first."""
    text = env_file.read_text() if env_file.exists() else ""
    match = LINE.search(text)
    existing = keys.parse(match.group(1).strip().strip("\"'")) if match else []
    new = keys.parse(entry)[0]
    if any(k.key_id == new.key_id for k in existing):
        raise CommandError(f"{env_file} already has a key called '{new.key_id}'.")
    parts = [entry]
    if match and match.group(1).strip():
        parts.append(match.group(1).strip().strip("\"'"))
    line = "SPP_ORG_KEYS=" + ",".join(parts)
    text = LINE.sub(lambda _: line, text, count=1) if match else text.rstrip("\n") + f"\n{line}\n"
    env_file.write_text(text)
    env_file.chmod(0o600)
    return [new.key_id, *(k.key_id for k in existing)]


class Command(BaseCommand):
    help = "Generate or list the organisation keys that protect .spp files."

    def add_arguments(self, parser: CommandParser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)
        generate = sub.add_parser("generate", help="Make a new key")
        generate.add_argument("--id", default="", help="Key id (default: key-YYYYMMDD)")
        generate.add_argument("--write-env", default="", help="Install it in this env file")
        sub.add_parser("list", help="Show installed key ids and fingerprints")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            if options["action"] == "list":
                ring = keys.ring()
                if not ring:
                    self.stdout.write(
                        "No organisation keys are configured (SPP_ORG_KEYS is empty)."
                    )
                for index, key in enumerate(ring):
                    role = "active: new files use it" if index == 0 else "kept for older files"
                    self.stdout.write(f"{key.key_id}  fingerprint {key.fingerprint}  ({role})")
                return
            key_id = options["id"] or f"key-{timezone.localdate():%Y%m%d}"
            entry = keys.generate(key_id)
            if options["write_env"]:
                ids = install(Path(options["write_env"]), entry)
                self.stdout.write(
                    f"Installed '{key_id}' in {options['write_env']} as the active key"
                    f" (keys now: {', '.join(ids)}). Restart the backend and worker."
                )
                self.stdout.write(
                    "Copy the SPP_ORG_KEYS line to every server that must open the same"
                    " files, over a secure channel, and keep a copy in a safe place:"
                    " without the key, .spp files can't be opened."
                )
            else:
                self.stdout.write(entry)
                self.stderr.write(
                    "Put this first in SPP_ORG_KEYS (keep the existing entries after it,"
                    " separated by commas), on every server that must open the same files."
                )
        except keys.KeyError_ as exc:
            raise CommandError(str(exc)) from exc
