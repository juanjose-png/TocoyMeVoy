---
name: django_admin_expert
description: >
  Experto en personalización de Django Admin. Capacidad para agregar métodos
  calculados en list_display, construir URLs de Drive dinámicamente y mostrar
  columnas enriquecidas con HTML seguro.
---

# Django Admin Expert

## Capacidades

1. **Columnas calculadas en `list_display`**
   - Agrega métodos de instancia al `ModelAdmin` que devuelven HTML renderizado.
   - Configura `short_description` para el encabezado de columna.

2. **URLs de Google Drive dinámicas**
   - Construye links de tipo `https://drive.google.com/drive/folders/{ID}` a partir de campos del modelo (p. ej. `drive_folder_id`).
   - Usa `format_html` para seguridad XSS.
   - Sigue la regla `target='_blank'` definida en `.agent/rules/django_ui_rules.md`.

3. **Manejo defensivo (null-safety)**
   - Si el campo de referencia de Drive está vacío o `None`, la columna muestra `"Sin soporte"` en lugar de lanzar error.

## Patrón estándar

```python
# admin.py
from django.contrib import admin
from django.utils.html import format_html
from .models import Invoice

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = [
        ..., "url_soporte",
    ]

    @admin.display(description="URL Soporte")
    def url_soporte(self, obj):
        if obj.drive_folder_id:
            url = f"https://drive.google.com/drive/folders/{obj.drive_folder_id}"
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">📂 Ver soporte</a>',
                url,
            )
        return "Sin soporte"
```

## Notas de implementación

- `drive_folder_id` se guarda en el modelo `Invoice` como `CharField(max_length=200, blank=True, default="")`.
- El ID de la carpeta se obtiene del retorno de `upload_invoice_in_folder()` en `tasks.py` y se persiste en el mismo save que `sheet_row` / `sheet_record_id`.
- No requiere `allow_tags`; `format_html` maneja el escape correctamente.
