from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('auth/login/', views.authenticate, name='token_obtain_pair'),
    path('auth/register/', views.register, name='register'),
    path('auth/password/change/', views.change_password),
    path('auth/password/forgot/', views.update_password),
    path('auth/password/update/', views.update_password),
    path('misc/fetch_account_details/', views.fetch_account_details),
    path('misc/fetch_banks/', views.fetch_banks),
    path('misc/update_phonebook/', views.update_phonebook),
    path('account/loans/', views.loans),
    path('account/notifications/', views.notifications),
    path('account/user/', views.get_user),
    path('account/docs/', views.docs)
]
