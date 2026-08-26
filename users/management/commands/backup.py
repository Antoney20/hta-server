import zipfile
import tempfile
from pathlib import Path
from datetime import datetime

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create a BPTAP backup containing database data, media files, and logs."

    def handle(self, *args, **options):

        base_dir = Path(settings.BASE_DIR)

        # backups/
        backup_dir = base_dir / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Example: BPTAP-26-08-2026.zip
        backup_date = datetime.now().strftime("%d-%m-%Y")
        backup_file = backup_dir / f"BPTAP-{backup_date}.zip"

        with tempfile.TemporaryDirectory() as temp_dir:

            temp_dir = Path(temp_dir)

            data_file = temp_dir / "data.json"
            media_file = temp_dir / "media.zip"
            logs_file = temp_dir / "logs.zip"

            self.stdout.write("Exporting database data...")

            with open(data_file, "w", encoding="utf-8") as file:
                management.call_command(
                    "dumpdata",
                    "--indent", "2",
                    "--natural-foreign",
                    "--natural-primary",
                    stdout=file,
                )

            self.stdout.write(
                self.style.SUCCESS("Database export completed.")
            )

            media_root = Path(settings.MEDIA_ROOT)

            self.stdout.write("Creating media archive...")

            with zipfile.ZipFile(
                media_file,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zipf:

                if media_root.exists():

                    for file_path in media_root.rglob("*"):

                        if file_path.is_file():

                            # Preserve media directory structure
                            arcname = file_path.relative_to(media_root)

                            zipf.write(
                                file_path,
                                arcname
                            )

            self.stdout.write(
                self.style.SUCCESS("Media archive completed.")
            )

            logs_root = base_dir / "logs"

            self.stdout.write("Creating logs archive...")

            with zipfile.ZipFile(
                logs_file,
                "w",
                zipfile.ZIP_DEFLATED
            ) as zipf:

                if logs_root.exists():

                    for file_path in logs_root.rglob("*"):

                        if file_path.is_file():

                            arcname = file_path.relative_to(logs_root)

                            zipf.write(
                                file_path,
                                arcname
                            )

            self.stdout.write(
                self.style.SUCCESS("Logs archive completed.")
            )
            
            self.stdout.write("Creating final BPTAP backup...")

            with zipfile.ZipFile(
                backup_file,
                "w",
                zipfile.ZIP_DEFLATED
            ) as backup_zip:

                backup_zip.write(
                    data_file,
                    "data.json"
                )

                backup_zip.write(
                    media_file,
                    "media.zip"
                )

                backup_zip.write(
                    logs_file,
                    "logs.zip"
                )


        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"BPTAP backup created successfully:"
            )
        )

        self.stdout.write(
            str(backup_file)
        )