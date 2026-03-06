from datetime import datetime

class PettyFlowValidator:
    """ Motor de validación para recargas de caja menor. """

    def __init__(self, monthly_budget):
        self.monthly_budget = monthly_budget

    def check_request_day(self, date_obj=None):
        """
        Valida si el día de la solicitud es Lunes o Martes para disparar alertas.
        0 = Lunes, 1 = Martes
        """
        if date_obj is None:
            date_obj = datetime.now()
            
        weekday = date_obj.weekday()
        if weekday in [0, 1]:
            return {
                'warning': True,
                'message': (
                    "Hemos recibido tu solicitud. Ten en cuenta que, por políticas de cajas menores, "
                    "las solicitudes realizadas los días lunes o martes se procesan para hacerse "
                    "efectivas a partir del miércoles. ¡Gracias por tu paciencia! Tu recarga está "
                    "en proceso; estamos siendo más ágiles que el área de sistemas cuando se cae el internet."
                )
            }
        return {'warning': False, 'message': ''}

    def validate_budget(self, assigned_budget, accumulated_reloads, requested_amount):
        """
        Valida el presupuesto 'Asignado' vs 'Recargas acumuladas' + nueva solicitud.
        """
        if accumulated_reloads + requested_amount > assigned_budget:
            return {
                'allowed': False,
                'error': f"Presupuesto excedido. Asignado: {assigned_budget}, Acumulado: {accumulated_reloads}, Solicitado: {requested_amount}"
            }
        return {'allowed': True}

    def is_first_of_month(self, date_obj=None):
        """ Verifica si es el día 1 del mes para resetear saldos. """
        if date_obj is None:
            date_obj = datetime.now()
        return date_obj.day == 1
