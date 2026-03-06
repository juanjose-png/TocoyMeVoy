from django.urls import path

from . import views

urlpatterns = [
    path("webhook", views.WebhookView.as_view(), name="webhook"),
    path("webhook/", views.WebhookView.as_view()),
    path("health/", views.HealthView.as_view(), name="health"),
]
