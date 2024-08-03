from django.db import models
from django.contrib.auth.models import AbstractUser, AbstractBaseUser, BaseUserManager
from django.utils import timezone
from loan_app.models import AppUser, Loan
from project_pack.models import Project, current_project, ProjectManager, ProjectQuerySet


class CustomUserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError('The phone must be set')
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(phone, password, **extra_fields)

    def get_queryset(self):
        return ProjectQuerySet(self.model, using=self._db).select_project()


class User(AbstractUser):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=100)
    phone = models.CharField(max_length=15, unique=True)
    password = models.CharField(max_length=100)
    level = models.CharField(max_length=50, default='admin')
    username = models.CharField(default='', max_length=100, blank=True, null=True)
    stage = models.CharField(default='', max_length=100, blank=True, null=True)
    stage_id = models.IntegerField(default=1)
    can_collect = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    status = models.BooleanField(default=True)
    last_login = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = 'phone'

    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f'{self.first_name} - {self.level.title()}: {self.stage}({self.stage_id}) ({self.pk})'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)

    class Meta:
        app_label = 'admin_panel'


class AdminLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    app_user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    action_type = models.CharField(max_length=100, blank=True, null=True)
    action = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"User {self.app_user.user_id}, logged by {self.user.stage}-{self.user.stage_id}"


class Note(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    app_user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    body = models.TextField(blank=True, null=True)
    modified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(blank=True, null=True)
    super = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.user.stage}-{self.user.stage_id} note on {self.app_user.first_name} ({self.app_user.user_id})"


class Collection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan = models.OneToOneField(Loan, on_delete=models.CASCADE)
    amount_due = models.FloatField(max_length=15, default=0)
    amount_paid = models.FloatField(max_length=10, default=0)
    stage = models.CharField(default='', max_length=10)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.user.stage}-{self.user.stage_id} Collection"


class LoanStatic(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    status = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)


class Repayment(models.Model):
    user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    tx_id = models.CharField(max_length=50, default='')
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    principal_amount = models.FloatField(max_length=10, default=0)
    amount_due = models.FloatField(max_length=10, default=0)
    amount_paid_now = models.FloatField(max_length=10, default=0)
    total_paid = models.FloatField(max_length=10, default=0)
    stage = models.CharField(max_length=20, default='A')
    overdue_days = models.IntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, default='')
    on_field = models.CharField(max_length=10, default='')
    allow = models.BooleanField(default=False)  # when admin forgives late repayment, allow = True

    def __str__(self):
        return f"{self.user.first_name} ({self.user.user_id}) Repayment"


class Progressive(models.Model):
    objects = ProjectManager()

    def save(self, *args, **kwargs):
        if not self.pk:
            self.project = current_project
        super().save(*args, **kwargs)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    disbursed_at = models.DateTimeField(null=True, blank=True)
    total_count = models.IntegerField(default=0)
    total_sum = models.FloatField(default=0)
    unpaid_count = models.IntegerField(default=0)
    unpaid_sum = models.FloatField(default=0)
    a_count = models.IntegerField(default=0)
    day0_count = models.IntegerField(default=0)
    day1_count = models.IntegerField(default=0)
    day2_count = models.IntegerField(default=0)
    day3_count = models.IntegerField(default=0)
    day4_count = models.IntegerField(default=0)
    day5_count = models.IntegerField(default=0)
    day6_count = models.IntegerField(default=0)
    day7_count = models.IntegerField(default=0)
    day8_count = models.IntegerField(default=0)
    day9_count = models.IntegerField(default=0)
    day10_count = models.IntegerField(default=0)
    day11_count = models.IntegerField(default=0)
    day12_count = models.IntegerField(default=0)
    day13_count = models.IntegerField(default=0)
    day14_count = models.IntegerField(default=0)
    day15_count = models.IntegerField(default=0)
    day16_count = models.IntegerField(default=0)
    day17_count = models.IntegerField(default=0)
    day18_count = models.IntegerField(default=0)
    day19_count = models.IntegerField(default=0)
    day20_count = models.IntegerField(default=0)
    day21_count = models.IntegerField(default=0)
    day22_count = models.IntegerField(default=0)
    day23_count = models.IntegerField(default=0)
    day24_count = models.IntegerField(default=0)
    day25_count = models.IntegerField(default=0)
    day26_count = models.IntegerField(default=0)
    day27_count = models.IntegerField(default=0)
    day28_count = models.IntegerField(default=0)
    day29_count = models.IntegerField(default=0)
    day30_count = models.IntegerField(default=0)
    day31_count = models.IntegerField(default=0)

    a_sum = models.FloatField(default=0)
    day0_sum = models.FloatField(default=0)
    day1_sum = models.FloatField(default=0)
    day2_sum = models.FloatField(default=0)
    day3_sum = models.FloatField(default=0)
    day4_sum = models.FloatField(default=0)
    day5_sum = models.FloatField(default=0)
    day6_sum = models.FloatField(default=0)
    day7_sum = models.FloatField(default=0)
    day8_sum = models.FloatField(default=0)
    day9_sum = models.FloatField(default=0)
    day10_sum = models.FloatField(default=0)
    day11_sum = models.FloatField(default=0)
    day12_sum = models.FloatField(default=0)
    day13_sum = models.FloatField(default=0)
    day14_sum = models.FloatField(default=0)
    day15_sum = models.FloatField(default=0)
    day16_sum = models.FloatField(default=0)
    day17_sum = models.FloatField(default=0)
    day18_sum = models.FloatField(default=0)
    day19_sum = models.FloatField(default=0)
    day20_sum = models.FloatField(default=0)
    day21_sum = models.FloatField(default=0)
    day22_sum = models.FloatField(default=0)
    day23_sum = models.FloatField(default=0)
    day24_sum = models.FloatField(default=0)
    day25_sum = models.FloatField(default=0)
    day26_sum = models.FloatField(default=0)
    day27_sum = models.FloatField(default=0)
    day28_sum = models.FloatField(default=0)
    day29_sum = models.FloatField(default=0)
    day30_sum = models.FloatField(default=0)
    day31_sum = models.FloatField(default=0)

    total_count_reloan = models.IntegerField(default=0)
    total_sum_reloan = models.FloatField(default=0)
    unpaid_count_reloan = models.IntegerField(default=0)
    unpaid_sum_reloan = models.FloatField(default=0)
    a_count_reloan = models.IntegerField(default=0)
    day0_count_reloan = models.IntegerField(default=0)
    day1_count_reloan = models.IntegerField(default=0)
    day2_count_reloan = models.IntegerField(default=0)
    day3_count_reloan = models.IntegerField(default=0)
    day4_count_reloan = models.IntegerField(default=0)
    day5_count_reloan = models.IntegerField(default=0)
    day6_count_reloan = models.IntegerField(default=0)
    day7_count_reloan = models.IntegerField(default=0)
    day8_count_reloan = models.IntegerField(default=0)
    day9_count_reloan = models.IntegerField(default=0)
    day10_count_reloan = models.IntegerField(default=0)
    day11_count_reloan = models.IntegerField(default=0)
    day12_count_reloan = models.IntegerField(default=0)
    day13_count_reloan = models.IntegerField(default=0)
    day14_count_reloan = models.IntegerField(default=0)
    day15_count_reloan = models.IntegerField(default=0)
    day16_count_reloan = models.IntegerField(default=0)
    day17_count_reloan = models.IntegerField(default=0)
    day18_count_reloan = models.IntegerField(default=0)
    day19_count_reloan = models.IntegerField(default=0)
    day20_count_reloan = models.IntegerField(default=0)
    day21_count_reloan = models.IntegerField(default=0)
    day22_count_reloan = models.IntegerField(default=0)
    day23_count_reloan = models.IntegerField(default=0)
    day24_count_reloan = models.IntegerField(default=0)
    day25_count_reloan = models.IntegerField(default=0)
    day26_count_reloan = models.IntegerField(default=0)
    day27_count_reloan = models.IntegerField(default=0)
    day28_count_reloan = models.IntegerField(default=0)
    day29_count_reloan = models.IntegerField(default=0)
    day30_count_reloan = models.IntegerField(default=0)
    day31_count_reloan = models.IntegerField(default=0)

    a_sum_reloan = models.FloatField(default=0)
    day0_sum_reloan = models.FloatField(default=0)
    day1_sum_reloan = models.FloatField(default=0)
    day2_sum_reloan = models.FloatField(default=0)
    day3_sum_reloan = models.FloatField(default=0)
    day4_sum_reloan = models.FloatField(default=0)
    day5_sum_reloan = models.FloatField(default=0)
    day6_sum_reloan = models.FloatField(default=0)
    day7_sum_reloan = models.FloatField(default=0)
    day8_sum_reloan = models.FloatField(default=0)
    day9_sum_reloan = models.FloatField(default=0)
    day10_sum_reloan = models.FloatField(default=0)
    day11_sum_reloan = models.FloatField(default=0)
    day12_sum_reloan = models.FloatField(default=0)
    day13_sum_reloan = models.FloatField(default=0)
    day14_sum_reloan = models.FloatField(default=0)
    day15_sum_reloan = models.FloatField(default=0)
    day16_sum_reloan = models.FloatField(default=0)
    day17_sum_reloan = models.FloatField(default=0)
    day18_sum_reloan = models.FloatField(default=0)
    day19_sum_reloan = models.FloatField(default=0)
    day20_sum_reloan = models.FloatField(default=0)
    day21_sum_reloan = models.FloatField(default=0)
    day22_sum_reloan = models.FloatField(default=0)
    day23_sum_reloan = models.FloatField(default=0)
    day24_sum_reloan = models.FloatField(default=0)
    day25_sum_reloan = models.FloatField(default=0)
    day26_sum_reloan = models.FloatField(default=0)
    day27_sum_reloan = models.FloatField(default=0)
    day28_sum_reloan = models.FloatField(default=0)
    day29_sum_reloan = models.FloatField(default=0)
    day30_sum_reloan = models.FloatField(default=0)
    day31_sum_reloan = models.FloatField(default=0)


class Waive(models.Model):
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE)
    waive_amount = models.FloatField(max_length=10, default=0)
    reason = models.CharField(max_length=10, default='PP')
    created_at = models.DateTimeField(default=timezone.now)
    modified_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, default='pending')


class Timeline(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    app_user = models.ForeignKey(AppUser, on_delete=models.CASCADE)
    name = models.CharField(max_length=50, default='')
    body = models.TextField(blank=True, null=True)
    detail = models.CharField(max_length=100, default='', blank=True)
    overdue_days = models.CharField(max_length=100, default='', blank=True)
    # 'Overdue 10 Days', 'Due Day'

    created_at = models.DateTimeField(default=timezone.now)


class Recovery(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)
    total_count = models.IntegerField(default=0)
    # total_count: total count of loans assigned to the collector

    amount_held = models.FloatField(default=0)
    # amount_held: total amount held by beginning of the day

    amount_paid = models.FloatField(default=0)
    # amount_paid: total amount paid by the end of the day

    paid_count = models.IntegerField(default=0)
    # paid_count: total count of loans repaid by the end of the day

    rate = models.FloatField(default=0)
    # rate: = (paid_count/total_count) * 100


class Logs(models.Model):
    action = models.CharField(max_length=100, default='', blank=True)
    body = models.TextField(default='', blank=True)
    status = models.CharField(max_length=20, default='info')
    fee = models.FloatField(default=0)
    created_at = models.DateTimeField(default=timezone.now)


class AcceptedUser(models.Model):
    admin_user = models.ForeignKey(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    created_at = models.DateTimeField(default=timezone.now)
