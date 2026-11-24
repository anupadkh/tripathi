from contextlib import closing
from pathlib import Path
import sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a consistent SQLite backup without overwriting an existing file."

    def add_arguments(self, parser):
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError(
                "For PostgreSQL, use pg_dump and your server backup policy."
            )
        source = Path(database["NAME"]).resolve()
        target = Path(options["output"]).resolve()
        if not source.is_file():
            raise CommandError("Source database does not exist.")
        if target.exists() or target == source:
            raise CommandError(
                "Choose a new backup filename; existing files will not be overwritten."
            )
        if not target.parent.is_dir():
            raise CommandError("Backup directory must already exist.")
        with (
            closing(
                sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
            ) as src,
            closing(sqlite3.connect(target)) as dst,
        ):
            src.backup(dst)
        self.stdout.write(self.style.SUCCESS(f"Backup created: {target}"))
