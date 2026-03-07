from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Employee(models.Model):
    cellphone = models.CharField(max_length=10, unique=True, verbose_name="Celular")  # 10 dígitos, sin prefijo 57
    sheet_name = models.CharField(max_length=100, unique=True, verbose_name="Hoja de cálculo")
    monthly_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Cupo Mensual")
    is_active = models.BooleanField(default=True, verbose_name="Activo")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última actualización")

    class Meta:
        ordering = ["sheet_name"]
        verbose_name = "Empleado"
        verbose_name_plural = "Empleados"

    def __str__(self):
        return f"{self.sheet_name} ({self.cellphone})"


class Invoice(models.Model):
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pendiente de confirmación"
        CONFIRMED = "confirmed", "Confirmada"
        ABANDONED = "abandoned", "Abandonada"
        ERROR     = "error",     "Error"

    employee = models.ForeignKey(
        "Employee",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="invoices",
        verbose_name="Empleado",
    )
    cellphone = models.CharField(max_length=15, verbose_name="Celular")  # incluye prefijo 57

    # Campos extraídos por Gemini
    invoice_date   = models.DateField(null=True, blank=True, verbose_name="Fecha factura")
    business_name  = models.CharField(max_length=255, blank=True, default="", verbose_name="Comercio")
    nit            = models.CharField(max_length=50, blank=True, default="", verbose_name="NIT")
    invoice_number = models.CharField(max_length=100, blank=True, default="", verbose_name="N° de factura")
    original_value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Valor original (IA)",
    )
    value = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name="Valor final",
    )
    was_corrected = models.BooleanField(default=False, verbose_name="Valor corregido por usuario")

    # Campos del usuario (opcionales)
    cost_center = models.CharField(max_length=255, blank=True, default="", verbose_name="Centro de costos")
    concept     = models.TextField(blank=True, default="", verbose_name="Concepto")

    # Archivo temporal (imagen/PDF) para subida a Drive
    file_path = models.CharField(max_length=500, blank=True, default="", verbose_name="Ruta archivo")
    is_pdf    = models.BooleanField(default=False, verbose_name="Es PDF")

    # Tracking Google Sheets
    sheet_row       = models.IntegerField(null=True, blank=True, verbose_name="Fila en Sheets")
    sheet_record_id = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID fila en Sheets")

    # Tracking Google Drive
    drive_folder_id = models.CharField(
        max_length=200, blank=True, default="",
        verbose_name="ID carpeta Drive",
    )
    
    # Traceability
    cufe = models.CharField(max_length=255, blank=True, default="", verbose_name="CUFE")
    check_odoo_doc = models.BooleanField(default=False, verbose_name="Check Odoo Doc")
    check_odoo_pago = models.BooleanField(default=False, verbose_name="Check Odoo Pago")
    difference = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Diferencia")
    observations = models.TextField(blank=True, default="", verbose_name="Observaciones")

    status     = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="Estado")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última actualización")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"

    def __str__(self):
        return f"#{self.pk} {self.business_name} — ${self.value} ({self.get_status_display()})"


class InvoiceSession(models.Model):
    class State(models.TextChoices):
        IDLE                  = "idle",                  "Inactivo"
        PROCESSING            = "processing_invoice",    "Procesando factura"
        WAITING_CONFIRMATION  = "waiting_confirmation",  "Esperando confirmación"
        WAITING_CORRECTION    = "waiting_correction",    "Esperando corrección de valor"
        WAITING_COST_CENTER   = "waiting_cost_center",   "Esperando centro de costos"
        WAITING_CONCEPT       = "waiting_concept",       "Esperando concepto"

    cellphone   = models.CharField(max_length=15, unique=True, verbose_name="Celular")  # incluye prefijo 57
    state       = models.CharField(
        max_length=30,
        choices=State.choices,
        default=State.IDLE,
        verbose_name="Estado",
    )
    current_invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="+",
        verbose_name="Factura actual",
    )

    # Campos legacy — se mantienen por backward compatibility
    last_row    = models.IntegerField(null=True, blank=True, verbose_name="Última fila")
    last_id     = models.CharField(max_length=50, null=True, blank=True, verbose_name="ID de fila")
    invoice_id  = models.CharField(max_length=100, null=True, blank=True, verbose_name="N° de factura")
    cost_center = models.TextField(null=True, blank=True, verbose_name="Centro de costos")

    created_at  = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at  = models.DateTimeField(auto_now=True, verbose_name="Última actualización")

    class Meta:
        verbose_name = "Sesión de factura"
        verbose_name_plural = "Sesiones de factura"

    def __str__(self):
        return f"{self.cellphone} — {self.get_state_display()}"


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El email es obligatorio.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email       = models.EmailField(unique=True, verbose_name="Correo electrónico")
    is_staff    = models.BooleanField(default=False, verbose_name="Es staff")
    is_active   = models.BooleanField(default=True, verbose_name="Activo")
    date_joined = models.DateTimeField(default=timezone.now, verbose_name="Fecha de registro")

    USERNAME_FIELD  = "email"
    REQUIRED_FIELDS = []  # createsuperuser solo pide email + password

    objects = CustomUserManager()

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

class PettyReload(models.Model):
    class Status(models.TextChoices):
        DRAFT    = "draft",    "Solicitud"
        APPROVED = "approved", "Aprobado"
        EXECUTED = "executed", "Realizado"
        CANCEL   = "cancel",   "Cancelado"

    reference = models.CharField(
        max_length=50, unique=True, editable=False, verbose_name="Referencia"
    )
    employee = models.ForeignKey(
        "Employee",
        on_delete=models.CASCADE,
        related_name="reloads",
        verbose_name="Empleado",
    )
    amount_requested = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Monto solicitado"
    )
    state = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Estado",
    )
    date_request = models.DateTimeField(
        default=timezone.now, verbose_name="Fecha de solicitud"
    )
    observations = models.TextField(blank=True, default="", verbose_name="Observaciones")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de creación")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Última actualización")

    class Meta:
        ordering = ["-date_request"]
        verbose_name = "Recarga de Caja Menor"
        verbose_name_plural = "Recargas de Caja Menor"

    def __str__(self):
        return f"{self.reference} — {self.employee.sheet_name} (${self.amount_requested})"

    def save(self, *args, **kwargs):
        if not self.reference:
            # Simple sequence generation logic for reference
            last_reload = PettyReload.objects.all().order_by('id').last()
            if not last_reload:
                self.reference = "RECH-0001"
            else:
                last_id = int(last_reload.reference.split('-')[1])
                self.reference = f"RECH-{str(last_id + 1).zfill(4)}"
        super().save(*args, **kwargs)
