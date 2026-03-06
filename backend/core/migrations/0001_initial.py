import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Employee",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cellphone", models.CharField(max_length=10, unique=True)),
                ("sheet_name", models.CharField(max_length=100)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
            options={
                "ordering": ["sheet_name"],
            },
        ),
        migrations.CreateModel(
            name="InvoiceSession",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("cellphone", models.CharField(max_length=15, unique=True)),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("idle", "Idle"),
                            ("processing_invoice", "Processing"),
                            ("waiting_cost_center", "Waiting Cost Center"),
                            ("waiting_concept", "Waiting Concept"),
                        ],
                        default="idle",
                        max_length=30,
                    ),
                ),
                ("last_row", models.IntegerField(blank=True, null=True)),
                (
                    "last_id",
                    models.CharField(blank=True, max_length=50, null=True),
                ),
                (
                    "invoice_id",
                    models.CharField(blank=True, max_length=100, null=True),
                ),
                ("cost_center", models.TextField(blank=True, null=True)),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True),
                ),
            ],
        ),
    ]
