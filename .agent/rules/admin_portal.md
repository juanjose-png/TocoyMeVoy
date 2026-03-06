# Reglas — Portal Administrativo Caja Menor

## Acceso
- El portal es de **acceso exclusivo para Estefania Olarte**.
- La autenticación se realiza mediante el sistema de sesiones de Django (`CustomUser`), usando su `email` como identificador.
- No se permite acceso anónimo a ninguna pantalla del portal. Cualquier request no autenticado redirige a `/portal/login/`.

## Navegación por pantallas

El flujo de navegación es estrictamente lineal:

```
Login → Pantalla A (Tarjetas) → Pantalla B (Meses) → Pantalla C (Tabla)
                 ↑_____________________________↑______________↑
                              (botón Volver)
```

### Pantalla A — Tarjetas
- Muestra una tarjeta visual por cada `Employee` activo.
- Cada tarjeta debe mostrar: **Nombre de la tarjeta** (`TARJETA`, extraído del `sheet_name`), **Líder** (`LIDER`, campo de la celda K8 del sheet), y opcionalmente el número de facturas del último mes.
- Al hacer clic en una tarjeta → navegar a Pantalla B con la tarjeta seleccionada.

### Pantalla B — Meses
- Lista los meses disponibles para la tarjeta seleccionada.
- Los meses se identifican leyendo las **filas de separador de fondo rojo** dentro de la hoja (ej. "ENERO 2025", "FEBRERO 2025").
- Mostrar solo meses del año actual (2026) por defecto. Permitir toggle para ver 2025.
- Al hacer clic en un mes → navegar a Pantalla C con la tarjeta + mes seleccionados.
- Botón **← Volver a tarjetas** en la parte superior.

### Pantalla C — Tabla de Datos
- Muestra la tabla completa de facturas del mes seleccionado con TODOS los campos:
  `No., Fecha, Nombre Negocio, NIT, N° Factura, Centro Costos, CONCEPTO, Valor Total, Valor Legalizado, **URL Drive**, **CUFE**, **Check Odoo Doc**, **Check Odoo Pago**, DIFERENCIA, OBSERVACIONES`.
- Respetar colores de celda: filas con fondo verde/amarillo mantienen ese color en la tabla HTML.
- Columna **URL Drive**: renderizar como enlace clicable que abra el archivo en Drive.
- Columnas **Check Odoo Doc** y **Check Odoo Pago**: mostrar ✅ / ❌ / vacío.
- Botón **← Volver a meses** en la parte superior.
- Botón **Exportar a Excel** en la parte superior derecha.

## Restricciones técnicas
- **NO modificar** las celdas del Sheet desde el portal. El portal es solo lectura.
- Las consultas a Sheets API se deben hacer via las funciones existentes en `google_sheets.py`.
- El portal vive en el mismo Django project, bajo el prefijo `/portal/`.
