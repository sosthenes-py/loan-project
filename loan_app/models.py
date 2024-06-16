from django.db import models
from django.utils import timezone
from project_pack.models import Project, ProjectManager, current_project


class AppUser(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
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
    eligible_amount = models.FloatField(default=6000)

    def __str__(self):
        return f'{self.first_name} ({self.user_id})'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)


class Document(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    file = models.FileField(upload_to='loan_app/docs/')
    description = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.first_name}'s Doc"


class Avatar(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='loan_app/avatar/')
    description = models.CharField(max_length=100, default='Profile Image')
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.first_name}'s Avatar"


class DisbursementAccount(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.first_name}'s Account Details"


class VirtualAccount(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    number = models.CharField(max_length=100, blank=True, null=True)
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=100, blank=True, null=True)

    objects = ProjectManager()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.first_name}'s Account Details"


class Contact(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=100)
    category = models.CharField(max_length=100, blank=True, null=True)


class Loan(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    loan_id = models.CharField(max_length=100)
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    principal_amount = models.FloatField(max_length=10, default=0)
    amount_disbursed = models.FloatField(max_length=10, default=0)
    # amount_disbursed = principal amount - interest
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

    objects = ProjectManager()

    def __str__(self):
        return f"N{self.principal_amount:,}; ID: {self.loan_id}; S: {self.status}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)



