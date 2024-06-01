from django.contrib.auth.backends import ModelBackend
from .models import User
from django.contrib.auth.models import User as AdminUser


class PhoneAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = User.objects.get(phone=username)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None


class AdminAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            user = AdminUser.objects.get(email=username)
            if user.check_password(password):
                return user
        except User.DoesNotExist:
            return None
