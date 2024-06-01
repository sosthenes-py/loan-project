from django.contrib import admin
from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings

urlpatterns = [
    path('', views.login_user, name='login'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('users/', views.users, name='users'),
    path('loans/', views.loans, name='loans'),
    path('repayments/', views.repayments, name='repayments'),
    path('analysis/', views.analysis, name='analysis'),
    path('logout/', views.logout_user, name='logout'),
    path('waiver/', views.waiver, name='waiver')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
