import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'solenium_project.settings')
django.setup()

from core.services.odoo_client import OdooClient
client = OdooClient()
if client.connect():
    # Buscar diarios de tipo banco o efectivo
    journals = client.models.execute_kw(client.db, client.uid, client.password, 'account.journal', 'search_read', [[('type', 'in', ['bank', 'cash'])]], {'fields': ['name', 'id', 'outbound_payment_method_line_ids']})
    for j in journals:
        print(f"ID: {j['id']} | Name: {j['name']}")
        p_methods = j.get('outbound_payment_method_line_ids', [])
        if p_methods:
            # Traer detalles de los métodos
            methods_details = client.models.execute_kw(client.db, client.uid, client.password, 'account.payment.method.line', 'read', [p_methods], {'fields': ['name']})
            for m in methods_details:
                print(f"  - Method ID: {m['id']} | Method Name: {m['name']}")
        else:
            print("  - No outbound payment methods found")
else:
    print("Failed to connect to Odoo")
