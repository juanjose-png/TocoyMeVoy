# Odoo Accounting Logic Rules

"Regla: 
1. Solo procesar facturas en estado 'Publicado' (posted). 
2. Si el estado es 'Borrador' (draft), marcar en la visual de Django como 'Pendiente en Odoo'. 
3. El campo 'Fecha de pago' debe coincidir exactamente con la fecha de la factura en Odoo. 
4. El Diario de pago debe buscarse por el nombre del titular de la tarjeta."
