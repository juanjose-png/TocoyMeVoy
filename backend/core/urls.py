from django.urls import path

from . import views

urlpatterns = [
    path("webhook", views.WebhookView.as_view(), name="webhook"),
    path("webhook/", views.WebhookView.as_view()),
    path("health/", views.HealthView.as_view(), name="health"),
    # API for Administrative Portal
    path("api/cards/", views.CardsListView.as_view(), name="cards-list"),
    path("api/cards/<str:sheet_name>/months/", views.CardMonthsView.as_view(), name="card-months"),
    path("api/cards/<str:sheet_name>/report/", views.ReportDataView.as_view(), name="report-data"),
    path("api/cards/<str:sheet_name>/sync-odoo/", views.SyncOdooMonthView.as_view(), name="sync-odoo"),
]
