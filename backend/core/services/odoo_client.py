import xmlrpc.client
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

class OdooClient:
    def __init__(self):
        self.url = getattr(settings, 'ODOO_URL', None)
        self.db = getattr(settings, 'ODOO_DB', None)
        self.username = getattr(settings, 'ODOO_USER', None)
        self.password = getattr(settings, 'ODOO_API_KEY', None)
        self.uid = None
        self.models = None

    def connect(self):
        try:
            common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            authenticated_uid = common.authenticate(self.db, self.username, self.password, {})
            if isinstance(authenticated_uid, int):
                self.uid = authenticated_uid
                self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
                return True
            return False
        except Exception as e:
            logger.error(f"Error connecting to Odoo: {e}")
            return False

    def get_invoice_by_ref(self, reference):
        """
        Busca una factura de proveedor por su número de referencia (ref).
        """
        if not self.uid:
            self.connect()
        
        domain = [('ref', '=', reference), ('move_type', '=', 'in_invoice')]
        try:
            results = self.models.execute_kw(self.db, self.uid, self.password,
                'account.move', 'search_read', [domain],
                {'fields': ['id', 'name', 'state', 'payment_state', 'invoice_date', 'amount_total']})
            return results[0] if results else None
        except Exception as e:
            logger.error(f"Error searching invoice {reference}: {e}")
            return None

    def register_payment(self, invoice_id, journal_name, payment_date):
        """
        Registra el pago de una factura en un diario específico.
        """
        if not self.uid:
            self.connect()

        try:
            # 1. Buscar Journal por nombre
            journal_domain = [('name', 'ilike', journal_name), ('type', 'in', ['bank', 'cash'])]
            journals = self.models.execute_kw(self.db, self.uid, self.password,
                'account.journal', 'search_read', [journal_domain], {'fields': ['id']})
            
            if not journals:
                return {'success': False, 'error': f"Journal '{journal_name}' no encontrado."}
            
            journal_id = journals[0]['id']

            # 2. Preparar el wizard de registro de pago
            wizard_vals = {
                'journal_id': journal_id,
                'payment_date': payment_date,
            }
            
            # En Odoo 14+ se usa account.payment.register
            context = {'active_model': 'account.move', 'active_ids': [invoice_id]}
            wizard_id = self.models.execute_kw(self.db, self.uid, self.password,
                'account.payment.register', 'create', [wizard_vals], {'context': context})
            
            # 3. Crear el pago
            self.models.execute_kw(self.db, self.uid, self.password,
                'account.payment.register', 'action_create_payments', [wizard_id], {'context': context})
            
            return {'success': True}
        except Exception as e:
            logger.error(f"Error registering payment for invoice {invoice_id}: {e}")
            return {'success': False, 'error': str(e)}
