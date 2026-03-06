from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .validation import PettyFlowValidator
import json
import os

class PettyReload(models.Model):
    _name = 'petty.reload'
    _description = 'Solicitud de Recarga de Caja Menor'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Referencia', required=True, copy=False, readonly=True, index=True, default=lambda self: _('Nuevo'))
    employee_id = fields.Many2one('res.users', string='Empleado', required=True, default=lambda self: self.env.user)
    employee_name = fields.Char(related='employee_id.name', string='Nombre Tarjeta', store=True)
    card_number = fields.Char(string='N° Tarjeta')
    amount_requested = fields.Float(string='Monto Solicitado', required=True)
    state = fields.Selection([
        ('draft', 'Solicitud'),
        ('approved', 'Aprobado'),
        ('executed', 'Realizado'),
        ('cancel', 'Cancelado')
    ], string='Estado', default='draft', tracking=True)
    
    date_request = fields.Datetime(string='Fecha de Solicitud', default=fields.Datetime.now)
    observations = fields.Text(string='Observaciones')

    @api.model
    def create(self, vals):
        if vals.get('name', _('Nuevo')) == _('Nuevo'):
            vals['name'] = self.env['ir.sequence'].next_by_code('petty.reload') or _('Nuevo')
        
        # Iniciar validador
        validator = PettyFlowValidator(0)
        
        # 1. Validar día de la semana (Lunes o Martes)
        day_check = validator.check_request_day()
        res = super(PettyReload, self).create(vals)
        
        if day_check['warning']:
            # Enviar mensaje irónico como nota en el registro
            res.message_post(
                body=day_check['message'],
                subtype_xmlid='mail.mt_comment',
                author_id=self.env.ref('base.partner_root').id # Simular bot
            )
        return res

    def action_approve(self):
        # Validar presupuesto antes de aprobar
        self._validate_budget_limits()
        self.write({'state': 'approved'})
        
        # Lógica de Visitadores: Notificar a Alan M en Discord
        self._notify_visitador_request()

    def action_execute(self):
        self.write({'state': 'executed'})
        # Enviar mensajes directos automáticos al Empleado y Administrador
        self._send_confirmation_notifications()
        
        # Enviar notificación al CANAL GENERAL PRIVADO de Discord
        self._send_discord_group_notification()
        
        # Sincronizar con Google Sheets
        self._sync_to_google_sheets()

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def _notify_visitador_request(self):
        """ Si el empleado es visitador, notificar a Alan M en Discord """
        visitadores = ['Mauro Madera', 'Milton Arcos', 'Julio Cesar', 'Benjamin Juli Owen', 'Bayron Cajica', 'Derwin Urdaneta']
        if self.employee_name in visitadores:
            msg = f"🔔 **Solicitud de Visitador** | @AlanM, el visitador **{self.employee_name}** ha solicitado una recarga por ${self.amount_requested}. Requiere tu aprobación previa."
            # Aquí se integraría la llamada asíncrona al bot o vía webhook
            self.message_post(body=f"Discord: {msg}")

    def _send_discord_group_notification(self):
        """ Notificación grupal en Discord tras ejecución exitosa """
        # Simulamos saldo restante (cupo - acumulado)
        saldo_mensual = 5000000 # Ejemplo, debería venir del motor de presupuesto
        msg = f"✅ **Recarga Exitosa** | @{self.employee_name}, tu recarga por ${self.amount_requested} ya está disponible. Tu saldo mensual restante es ${saldo_mensual - self.amount_requested}. Vigencia hasta fin de mes."
        self.message_post(body=f"Discord Group: {msg}")

    def _sync_to_google_sheets(self):
        """ Llamada al servicio de sincronización. """
        try:
            from ..utils.google_sheets_sync import GoogleSheetsSync
            sync_service = GoogleSheetsSync(spreadsheet_id='REPLACE_WITH_ID', credentials_path='path/to/creds.json')
            data = {
                'referencia': self.name,
                'empleado': self.employee_name,
                'monto': self.amount_requested,
                'fecha': str(self.date_request),
                'observaciones': self.observations or ''
            }
            sync_service.sync_reload(data)
        except Exception as e:
            self.message_post(body=f"⚠️ Error de sincronización: {str(e)}")

    def _validate_budget_limits(self):
        """ Valida contra el archivo JSON de presupuestos iniciales. """
        file_path = os.path.join(os.path.dirname(__file__), '../../.agent/data/presupuestos_iniciales.json')
        if not os.path.exists(file_path):
            return
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Buscar empleado en la tabla
        limit_data = next((item for item in data if item['tarjeta'].lower() == self.employee_name.lower()), None)
        
        if limit_data:
            budget_limit = limit_data.get('monto_por_recarga')
            if isinstance(budget_limit, (int, float)) and self.amount_requested > budget_limit:
                raise ValidationError(_(
                    "El monto solicitado (%s) supera el estándar permitido para esta tarjeta (%s). "
                    "Por favor, ajusta el monto o solicita aprobación manual."
                ) % (self.amount_requested, budget_limit))
            
            if limit_data.get('cupo_mensual') == "Pendiente de aprobación manual":
                 self.message_post(body=_("ATENCIÓN: Este perfil requiere validación manual de cupo (Visitador)."))

    def _send_confirmation_notifications(self):
        """ Notificación a 3 bandas: Empleado, Admin, Tesorería. """
        body = _(
            "✅ **Recarga Confirmada**\n"
            "Monto: %s\n"
            "Saldo restante estimado: [Consultar Odoo]\n"
            "Vigencia: Inmediata"
        ) % (self.amount_requested)
        
        # Publicar en el chatter (notifica a administradores y seguidores)
        self.message_post(body=body, subtype_xmlid='mail.mt_comment')
        
        # Aquí se podría implementar el envío de mensaje directo (DM) 
        # usando mail.channel si estuviera configurado.
