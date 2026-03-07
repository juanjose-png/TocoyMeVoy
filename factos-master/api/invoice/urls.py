from django.urls import path
from api.invoice import views


urlpatterns = [
    path('zapier/',  views.SaveLinkView.as_view(), name='save_link'),
]