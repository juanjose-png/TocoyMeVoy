import base64
from abc import ABC, abstractmethod
from invoice import models as invoice_models

from invoice.odoo.odoo_manager import Odoo
from elastic_logging.logger import elastic_logger

class OdooSupportDocumentError(Exception):
    def __init__(self, message, status: invoice_models.Invoice.Status, model=None):
        self.status = status
        if model:
            self.message = f"Model {model} {message}"
        else:
            self.message = message
        super().__init__(self.message)

class OdooSupportDocument(ABC):

    @property
    def invoice_identifier(self):
        """Returns invoice_number if available, otherwise invoice pk"""
        return self.invoice_obj.invoice_number or f"ID-{self.invoice_obj.pk}"

    @classmethod
    def create(cls, invoice_obj: invoice_models.Invoice) -> 'OdooSupportDocument':
        """Factory method para crear el documento apropiado"""
        invoice_id = invoice_obj.invoice_number or f"ID-{invoice_obj.pk}"
        if invoice_obj.order_number:
            return OdooSupportDocumentPurchaseOrder(invoice_obj)
        else:
            return OdooSupportDocumentSupplierInvoice(invoice_obj)
    
    @abstractmethod
    def create_invoice(self):
        pass

    def register_move_id_in_invoice(self):
        try:
            elastic_logger.info(f"Registering move_id for invoice {self.invoice_identifier}")
            # Check that rx_odoo_invoice exists
            if not self.invoice_obj.rx_odoo_invoice:
                raise Exception("Invoice doesn't have rx_odoo_invoice field")

            # First validate that all elements have res_id
            for element in self.invoice_obj.rx_odoo_invoice:
                if 'res_id' not in element:
                    raise Exception(f"Missing res_id in invoice element: {element}")

            # Only create objects if all validations pass
            for element in self.invoice_obj.rx_odoo_invoice:
                account_move_obj = invoice_models.AccountMove.objects.create(
                    move_id=element['res_id']
                )
                account_move_obj.invoice.add(self.invoice_obj)
            elastic_logger.info(f"Successfully registered move_id for invoice {self.invoice_identifier}")
        except Exception as e:
            raise OdooSupportDocumentError(
                e.message,
                invoice_models.Invoice.State.REGISTERED_BUT_NOT_MOVE_ID,
                self.invoice_obj
            )

    def load_attachment(self):
        try:
            elastic_logger.info(f"Loading attachment for invoice {self.invoice_identifier}")
            invoice_pdf = self.invoice_obj.invoice_pdf
            if not invoice_pdf:
                raise Exception("Invoice doesn't have invoice file")

            with open(invoice_pdf.path, 'rb') as file:
                file_content = file.read()
                encoded_data = base64.b64encode(file_content).decode('utf-8')

            attachment_odoo = Odoo('ir.attachment')
            query = self.invoice_obj.accountmove_set.all()

            for account_move_obj in query:
                attachment_odoo.create({
                    'name': self.invoice_obj.invoice_pdf.name,
                    'res_model': 'account.move',
                    'res_id': account_move_obj.move_id,
                    'type': 'binary',
                    'datas': encoded_data,
                    'mimetype': 'application/pdf'
                })
            elastic_logger.info(f"Successfully loaded attachment for invoice {self.invoice_identifier}")
        except Exception as e:
            raise OdooSupportDocumentError(
                str(e),
                invoice_models.Invoice.Status.REGISTERED_BUT_NOT_ATTACHMENT,
                self.invoice_obj
            )

    def set_state_registered_complete(self):
        self.invoice_obj.status = invoice_models.Invoice.Status.REGISTERED_COMPLETE
        self.invoice_obj.save()  

    
class OdooSupportDocumentPurchaseOrder(OdooSupportDocument):

    def __init__(self, invoice_obj: invoice_models.Invoice):
        self.invoice_obj = invoice_obj
        self.purchase_order = Odoo('purchase.order')
    
    def create_invoice(self):
        """Create supplier invoice in Odoo from the .ZIP file.
        Returns:
            boolean: Check if the invoices were created.
        """
        try:
            elastic_logger.info(f"Starting purchase order invoice creation for {self.invoice_identifier}")
            # Validate if the invoice has a purchase order
            order_number = self.invoice_obj.order_number
            if not order_number:
                raise ValueError(f'La factura {self.invoice_obj.invoice_number} no tiene un número de orden de compra.')

            created_invoices = self.__create_invoice_with_purchase_order()

            self.invoice_obj.rx_odoo_invoice = [created_invoices]
            self.invoice_obj.save()

            self.register_move_id_in_invoice()
            self.load_attachment()
            self.set_state_registered_complete()

            elastic_logger.info(f"Successfully created purchase order invoice for {self.invoice_identifier}")
            return True
        except Exception as e:
            elastic_logger.error(f"Failed to create purchase order invoice for {self.invoice_identifier}: {str(e)}")
            self.invoice_obj.rx_odoo_invoice_error = str(e)
            self.invoice_obj.save()
            return False

    def __create_invoice_with_purchase_order(self):
        """Create invoice in Odoo from the filtered invoices with purchase order.
        Returns:
            list: List of created invoices.
        """
        # Create invoice with purchase order
        purchase_order_id = self.get_purchase_order_id(self.invoice_obj.order_number)
        invoice_result = self.create_invoice_from(purchase_order_id)

        return invoice_result


    def get_purchase_order_id(self, name):
        """Get purchase order ID from Odoo by name.
        Args:
            name (str): Name of the purchase order.

        Returns:
            int: ID of the purchase order.
        """
        purchase_order_id = self.purchase_order.filter(
            fields=['id'],
            filter=[['name', '=', name]],
        )
        if not purchase_order_id:
            elastic_logger.error(f"Purchase order not found in Odoo: {name}")
            raise OdooSupportDocumentError(
                f'No se encontró la orden de compra {name} en Odoo.',
                invoice_models.Invoice.Status.PROBLEM_WITH_ODOO,
                self.invoice_obj
            )
        return purchase_order_id[0]['id']
        

    def create_invoice_from(self, purchase_order_id):
        """Create invoice from purchase order in Odoo.
        Args:
            purchase_order_id (int): ID of the purchase order.
        Returns:
            Object: Result of the invoice creation.

        """
        try:
            result = self.purchase_order.models.execute_kw(
                self.purchase_order.db,
                self.purchase_order.uid,
                self.purchase_order.password,
                self.purchase_order.model_name,
                'action_create_invoice',
                [[purchase_order_id]],
            )
            return result
        except Exception as e:
            elastic_logger.error(f"Failed to create invoice from purchase order {purchase_order_id}: {str(e)}")
            raise OdooSupportDocumentError(
                f'Creation of invoice using purchase order failed',
                invoice_models.Invoice.Status.PROBLEM_WITH_ODOO,
                self.invoice_obj
            )
   
            
class OdooSupportDocumentSupplierInvoice(OdooSupportDocument):

    def __init__(self, invoice_obj: invoice_models.Invoice):
        self.invoice_obj = invoice_obj
        self.supplier_invoice = Odoo('l10n_co_cei.supplier_invoice')
    

    def create_invoice(self):
        """Create supplier invoice in Odoo from the .ZIP file.
        Returns:
            boolean: Check if the invoices were created.
        """
        try:
            elastic_logger.info(f"Starting supplier invoice creation for {self.invoice_identifier}")

            self.zip_base64 = self._get_zip_base_64()
            self.wizard_id = self._create_wizard(self.zip_base64)
            self.result_dict = self._charge_supplier_invoice(self.wizard_id)

            self.invoice_obj.rx_odoo_invoice = [self.result_dict]
            self.invoice_obj.registered_in_odoo = True
            self.invoice_obj.save()

            self.register_move_id_in_invoice()
            self.load_attachment()
            self.set_state_registered_complete()

            elastic_logger.info(f"Successfully created supplier invoice for {self.invoice_identifier}")
            return True
        except OdooSupportDocumentError as e:
            elastic_logger.error(f"Failed to create supplier invoice for {self.invoice_identifier}: {str(e)}")
            self.invoice_obj.rx_odoo_invoice_error = str(e)
            self.invoice_obj.status = e.status
            self.invoice_obj.save()
            return False


    def _get_zip_base_64(self):
        """
            Get the ZIP file in base 64 from the invoice object.
        Returns:
            str: ZIP file in base 64.
        """

        # Check that the invoice_obj has invoice_file
        if not self.invoice_obj.invoice_file:
            raise OdooSupportDocumentError(
                'invoice_file is empty', invoice_models.Invoice.Status.PROBLEM_WITH_FACTOS, self.invoice_obj
            )


        # Check that the file is a ZIP file
        if not self.invoice_obj.invoice_file.name.endswith('.zip'):
            raise OdooSupportDocumentError(
                f'invoice_file is not a ZIP file', invoice_models.Invoice.Status.PROBLEM_WITH_FACTOS, self.invoice_obj
            )

        try:
            zip_file_path = self.invoice_obj.invoice_file.path
            with open(zip_file_path, 'rb') as f:
                file_content = f.read()
                zip_base64 = base64.b64encode(file_content).decode('utf-8')
            return zip_base64
        except Exception as e:
            raise OdooSupportDocumentError(
                f'Error reading the ZIP file: {str(e)}', invoice_models.Invoice.Status.PROBLEM_WITH_FACTOS, self.invoice_obj
            )

    def _create_wizard(self, zip_base64):
        """
            Create the wizard to import the supplier invoice in Odoo.
        Returns:
            int: ID of the created wizard.
        """
        try:
            wizard_id = self.supplier_invoice.create({
                'file': zip_base64
            })
            return wizard_id
        except Exception as e:
            elastic_logger.error(f"Failed to create supplier invoice wizard: {str(e)}")
            raise OdooSupportDocumentError(
                f'Error creating the supplier_invoice wizard: {str(e)}',
                invoice_models.Invoice.Status.PROBLEM_WITH_ODOO,
                self.invoice_obj
            )
        
    def _charge_supplier_invoice(self, wizard_id):
        """
            Charge the supplier invoice in Odoo.
        Returns:
            Dict: Result of the supplier invoice creation.
            {
                'res_model': 'account.move',
                'res_id': 115689
            }
        """
        try:
            result_dict = self.supplier_invoice.call_method("charge_supplier_invoice", [wizard_id])
            return result_dict
        except Exception as e:
            elastic_logger.error(f"Failed to charge supplier invoice with wizard {wizard_id}: {str(e)}")
            raise OdooSupportDocumentError(
                f'Error using the charge_supplier_invoice: {str(e)}',
                invoice_models.Invoice.Status.PROBLEM_WITH_ODOO,
                self.invoice_obj
            )