from django import forms
from .models import User


class RegisterForm(forms.ModelForm):
    CHOICES = [
        ('super admin', 'Super Admin'),
        ('admin', 'Admin'),
        ('approval admin', 'Approval Admin'),
        ('team leader', 'Team Leader'),
        ('staff', 'Staff')

    ]
    level = forms.ChoiceField(choices=CHOICES)
    code = forms.CharField(max_length=20)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'email', 'password', 'code', 'level']

    def clean_code(self):
        if self.cleaned_data.get('code') != '1234':
            raise forms.ValidationError('Code error')


class LoginForm(forms.Form):
    phone = forms.CharField(required=True)
    password = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ['phone', 'password']
