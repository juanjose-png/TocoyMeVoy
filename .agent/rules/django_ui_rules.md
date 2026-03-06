# Django UI Rules

## Regla: Links externos en Django Admin

Toda URL externa mostrada en el Admin de Django debe abrirse en una pestaña nueva (`target='_blank'`).
Usa `format_html` (de `django.utils.html`) para asegurar que el HTML del enlace sea renderizado correctamente por el framework y no escapado como texto plano.

### Ejemplo correcto

```python
from django.utils.html import format_html

def url_soporte(self, obj):
    if obj.drive_folder_id:
        url = f"https://drive.google.com/drive/folders/{obj.drive_folder_id}"
        return format_html('<a href="{}" target="_blank">📂 Ver soporte</a>', url)
    return "Sin soporte"
url_soporte.short_description = "URL Soporte"
```

### Por qué importa

- `format_html` escapa automáticamente los argumentos dinámicos (protección XSS).
- Marcar el método con `.allow_tags = True` está **deprecado** desde Django 2.0; `format_html` es el reemplazo oficial.
- `target='_blank'` mejora la experiencia del usuario al no interrumpir la sesión del Admin.
