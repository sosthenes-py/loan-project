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
    username = models.CharField(max_length=15, default='')
    phone2 = models.CharField(default='', max_length=15, blank=True, null=True)
    bvn = models.CharField(max_length=20, default='', blank=True, null=True)
    email2 = models.EmailField(default='', blank=True, null=True)
    address = models.CharField(max_length=100, default='', blank=True, null=True)
    status = models.BooleanField(default=False)  # Docs status
    status_reason = models.TextField(default='')  # Docs rejection reason
    created_at = models.DateTimeField(default=timezone.now)
    last_access = models.DateTimeField(default=timezone.now)
    user_id = models.CharField(max_length=20)
    dob = models.DateField(default=timezone.now)
    password = models.CharField(max_length=100)
    gender = models.CharField(max_length=100, default='male')
    state = models.CharField(max_length=100, default='', blank=True, null=True)
    lga = models.CharField(max_length=100, default='', blank=True, null=True)
    eligible_amount = models.FloatField(default=10000)
    marital_status = models.CharField(max_length=100, default='')
    nationality = models.CharField(max_length=100, default='', blank=True, null=True)
    children = models.CharField(max_length=100, default='', blank=True, null=True)
    education = models.CharField(max_length=100, default='')
    employment = models.CharField(max_length=100, default='', blank=True, null=True)
    borrow_level = models.IntegerField(default=1)
    suspend = models.BooleanField(default=False)

    def is_blacklisted(self):
        return hasattr(self, 'blacklist')

    def date_blacklisted(self):
        if self.is_blacklisted():
            return f"{getattr(self, 'blacklist').created_at:%b %d}"
        else:
            return ''

    def __str__(self):
        return f'{self.first_name} ({self.user_id})'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)


class Document(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    file = models.FileField(upload_to='loan_app/docs/', blank=True, null=True)
    name = models.CharField(max_length=100, default='')
    description = models.CharField(max_length=100)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.first_name}'s Doc"


class Avatar(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    file = models.ImageField(upload_to='loan_app/avatar/', blank=True, null=True)
    name = models.CharField(max_length=100, default='')
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
    name = models.CharField(max_length=1000, blank=True, null=True)
    phone = models.CharField(max_length=1000)
    category = models.CharField(max_length=1000, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)


class CallLog(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=1000, blank=True, null=True)
    phone = models.CharField(max_length=1000)
    category = models.CharField(max_length=1000, blank=True, null=True)
    date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    timestamp = models.CharField(max_length=50, default='')


class SmsLog(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=10000, blank=True, null=True)
    phone = models.CharField(max_length=10000)
    message = models.TextField()
    category = models.CharField(max_length=5000)
    date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Name: {self.name}"


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
    duration = models.IntegerField(default=4)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    disbursed_at = models.DateTimeField(blank=True, null=True)
    repaid_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=100, default='pending')
    reloan = models.IntegerField(default=1)
    interest_perc = models.FloatField(default=40)
    decline_reason = models.TextField(blank=True, null=True)
    disburse_id = models.CharField(max_length=20, default='')  # flw transfer ID
    purpose = models.CharField(max_length=100, default='')

    objects = ProjectManager()

    def __str__(self):
        return f"N{self.principal_amount:,}; ID: {self.loan_id}; S: {self.status}"

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)


class Blacklist(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    reason = models.CharField(max_length=10, default='overdue')
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(blank=True, null=True)


class Notification(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    message = models.TextField()
    message_type = models.CharField(max_length=50, default='system')
    viewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)


class Otp(models.Model):
    user = models.OneToOneField(AppUser, on_delete=models.CASCADE)
    code = models.CharField(max_length=20)
    expires_at = models.DateTimeField(null=True, blank=True)

