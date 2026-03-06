import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Employee

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Employee)
def employee_saved(sender, instance:Employee, created, **kwargs):
    action = "creado" if created else "actualizado"
    logger.info("Employee %s (%s).", instance.cellphone, action)

    if created:
        from core.tasks import create_employee_drive_folder
        create_employee_drive_folder.delay(instance.cellphone, instance.sheet_name)
        logger.info("Task create_employee_drive_folder encolada para %s.", instance.cellphone)


@receiver(post_delete, sender=Employee)
def employee_deleted(sender, instance:Employee, **kwargs):
    logger.info("Employee %s eliminado.", instance.cellphone)
