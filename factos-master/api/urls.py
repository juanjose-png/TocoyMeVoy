from django.urls import path, include
from api.invoice import views


urlpatterns = [
    path('invoice/', include('api.invoice.urls')),
]