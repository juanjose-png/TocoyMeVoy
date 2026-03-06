import json

from django.core.management.base import BaseCommand

from core.models import Employee


class Command(BaseCommand):
    help = "Carga los empleados iniciales desde config/cellphones_sheets.json a la base de datos."

    def handle(self, *args, **kwargs):
        try:
            with open("config/cellphones_sheets.json") as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write("Archivo config/cellphones_sheets.json no encontrado.")
            return

        created_count = 0
        updated_count = 0

        for cellphone, sheet_name in data.items():
            _, was_created = Employee.objects.update_or_create(
                cellphone=cellphone,
                defaults={"sheet_name": sheet_name, "is_active": True},
            )
            if was_created:
                created_count += 1
            else:
                updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Completado: {created_count} creados, {updated_count} actualizados. "
                f"Total en DB: {Employee.objects.count()}"
            )
        )
