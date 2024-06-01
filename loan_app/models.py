from django.db import models
from django.utils import timezone


# Create your models here.
class AppUser(models.Model):
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField()
    phone = models.CharField(unique=True, max_length=15)
    phone2 = models.CharField(default='', max_length=15, blank=True, null=True)
    bvn = models.CharField(max_length=20, default='', blank=True, null=True)
    email2 = models.EmailField(default='', blank=True, null=True)
    address = models.CharField(max_length=100, default='', blank=True, null=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_access = models.DateTimeField(default=timezone.now)
    user_id = models.CharField(max_length=20)
    dob = models.DateField(default=timezone.now)
    password = models.CharField(max_length=100)
    gender = models.CharField(max_length=100, default='male')
    state = models.CharField(max_length=100, default='', blank=True, null=True)
    lga = models.CharField(max_length=100, default='', blank=True, null=True)

    def __str__(self):
        return f'{self.first_name} ({self.user_id})'

    class Meta:
        app_label = 'loan_app'


class Document(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='loan_app/docs/')
    description = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.first_name}'s Doc"

    class Meta:
        app_label = 'loan_app'


class Avatar(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='loan_app/avatar/')
    description = models.CharField(max_length=100, default='Profile Image')
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = 'loan_app'

    def __str__(self):
        return f"{self.user.first_name}'s Avatar"


class Employment(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True, null=True, default=None)
    state = models.CharField(max_length=100, default='', blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True, default=None)
    complex = models.CharField(max_length=100, blank=True, null=True, default=None)
    role = models.CharField(max_length=100, blank=True, null=True, default=None)
    duration = models.CharField(max_length=100, blank=True, null=True, default=None)
    salary = models.CharField(max_length=100, blank=True, null=True, default=None)
    hr_name = models.CharField(max_length=100, blank=True, null=True, default=None)
    hr_phone = models.CharField(max_length=100, blank=True, null=True, default=None)
    hr_email = models.CharField(max_length=100, blank=True, null=True, default=None)

    def __str__(self):
        return f"{self.user.first_name}'s Employment"


class Emergency(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    family_name = models.CharField(max_length=100, blank=True, null=True, default=None)
    family_phone = models.CharField(max_length=100, blank=True, null=True)
    family_relationship = models.CharField(max_length=100, blank=True, null=True)
    family_email = models.CharField(max_length=100, blank=True, null=True)
    family_occupation = models.CharField(max_length=100, blank=True, null=True)
    colleague_name = models.CharField(max_length=100, blank=True, null=True, default=None)
    colleague_phone = models.CharField(max_length=100, blank=True, null=True)
    colleague_email = models.CharField(max_length=100, blank=True, null=True)
    colleague_occupation = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name}'s Emergency"


class Guarantor(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=100, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    occupation = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name}'s Guarantors"


class DisbursementAccount(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name}'s Account Details"


class VirtualAccount(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name}'s Account Details"


class Loan(models.Model):
    loan_id = models.CharField(max_length=100)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    principal_amount = models.FloatField(max_length=10, default=0)
    amount_disbursed = models.FloatField(max_length=10, default=0)
    # amount_loaned = principal amount - interest
    amount_due = models.FloatField(max_length=10, default=0)
    # amount_due = principal amount (overdue charges will accumulate here too)
    amount_paid = models.FloatField(max_length=10, default=0)
    duration = models.IntegerField(default=6)
    created_at = models.DateTimeField(default=timezone.now)
    disbursed_at = models.DateTimeField(blank=True, null=True)
    repaid_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=100, default='pending')
    reloan = models.IntegerField(default=1)
    # for reloan, 1 for first loan, 2 > for reloan, value being actual number of reloans

    def __str__(self):
        return f"N{self.principal_amount:,}; ID: {self.loan_id}; S: {self.status}"


