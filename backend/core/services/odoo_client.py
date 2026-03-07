import xmlrpc.client
import logging
import ssl
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
        print(f"DEBUG ODOO: Intentando conectar a {self.url} | DB: {self.db} | User: {self.username}")
        if not self.url or not self.db or not self.username or not self.password:
            print("DEBUG ODOO: Faltan variables de configuración")
            return False

        try:
            # Contexto SSL para ignorar verificación de certificados (util en Docker/Dev)
            context = ssl._create_unverified_context()
            
            common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common', context=context)
            authenticated_uid = common.authenticate(self.db, self.username, self.password, {})
            
            print(f"DEBUG ODOO: Resultado autenticación: {authenticated_uid}")
            if isinstance(authenticated_uid, int):
                self.uid = authenticated_uid
                self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object', context=context)
                print(f"DEBUG ODOO: Autenticación exitosa. UID: {self.uid}")
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
            if not self.connect():
                return None
        
        ref_clean = reference.strip()
        domain = [('ref', 'ilike', ref_clean), ('move_type', '=', 'in_invoice')]
        try:
            logger.info(f"Buscando factura en Odoo con ref: {ref_clean}")
            results = self.models.execute_kw(self.db, self.uid, self.password,
                'account.move', 'search_read', [domain],
                {'fields': ['id', 'name', 'state', 'payment_state', 'invoice_date', 'amount_total']})
            
            if results:
                # Filtrar por coincidencia exacta si hay varios, o tomar el primero
                exact_match = next((r for r in results if r['ref'] == ref_clean), results[0])
                logger.info(f"Factura encontrada en Odoo: {exact_match['name']} (ID: {exact_match['id']})")
                return exact_match
            logger.warning(f"No se encontró factura en Odoo con ref: {ref_clean}")
            return None
        except Exception as e:
            logger.error(f"Error searching invoice {reference}: {e}")
            return None

    def register_payment(self, invoice_id, journal_name, payment_date, amount):
        """
        Registra el pago de una factura en un diario específico.
        """
        if not self.uid:
            self.connect()

        logger.info(f"Iniciando registro de pago: Invoice ID {invoice_id}, Journal {journal_name}, Date {payment_date}, Amount {amount}")

        try:
            # 1. Buscar Journal por nombre
            journal_domain = [('name', 'ilike', journal_name), ('type', 'in', ['bank', 'cash'])]
            journals = self.models.execute_kw(self.db, self.uid, self.password,
                'account.journal', 'search_read', [journal_domain], {'fields': ['id', 'name']})
            
            if not journals:
                logger.warning(f"Journal '{journal_name}' no encontrado. Intentando con nombre parcial...")
                # Reintento con búsqueda más amplia si falla
                journal_domain = [('name', 'ilike', journal_name.split(' ')[0])]
                journals = self.models.execute_kw(self.db, self.uid, self.password,
                    'account.journal', 'search_read', [journal_domain], {'fields': ['id', 'name']})

            if not journals:
                return {'success': False, 'error': f"Journal '{journal_name}' no encontrado en Odoo."}
            
            journal_id = journals[0]['id']
            logger.info(f"Journal encontrado: {journals[0]['name']} (ID: {journal_id})")

            # 2. Preparar el wizard de registro de pago
            wizard_vals = {
                'journal_id': journal_id,
                'payment_date': payment_date,
                'amount': float(amount),
                'payment_method_line_id': False, # Odoo suele determinarlo solo, pero se puede especificar
            }
            
            # En Odoo 14+ se usa account.payment.register
            context = {'active_model': 'account.move', 'active_ids': [invoice_id]}
            logger.info(f"Creando wizard de pago con vals: {wizard_vals}")
            
            wizard_id = self.models.execute_kw(self.db, self.uid, self.password,
                'account.payment.register', 'create', [wizard_vals], {'context': context})
            
            # 3. Crear el pago
            logger.info(f"Ejecutando action_create_payments para wizard {wizard_id}")
            self.models.execute_kw(self.db, self.uid, self.password,
                'account.payment.register', 'action_create_payments', [wizard_id], {'context': context})
            
            logger.info("Pago registrado exitosamente en Odoo.")
            return {'success': True}
        except Exception as e:
            logger.error(f"Error registering payment for invoice {invoice_id}: {e}")
            return {'success': False, 'error': str(e)}
