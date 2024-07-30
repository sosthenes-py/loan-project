import django.db.models
from django.utils import timezone
import datetime as dt
from django.db.models import Sum, Count, Case, When, Value, F, DecimalField, Q
from django.db.models.functions import TruncDay, TruncMonth
from calendar import monthrange
import random
import math
from admin_panel.models import User as AdminUser, AdminLog, Note, Collection, LoanStatic, Repayment, Progressive, Waive, Timeline, Recovery, Logs, AcceptedUser
from loan_app.models import AppUser, Document, DisbursementAccount, Loan, SmsLog, Contact, Blacklist
from django.contrib.auth.hashers import make_password, check_password
from faker import Faker
import loan_app.api as apis
import json
import phonenumbers


LOAN_DURATION = 5
LEVEL1_BASE_AMOUNT = 10000
LEVEL2_BASE_AMOUNT = 20000
LEVEL3_BASE_AMOUNT = 50000


class Func:
    @staticmethod
    def format_phone(phone):
        parsed_number = phonenumbers.parse(phone, 'NG')
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL).replace(' ', '')

    @staticmethod
    def format_agent_id(num: int):
        if num < 10:
            return f'00{num}'
        else:
            return f'0{num}'

    @staticmethod
    def overdue_days(disbursed_at, duration):
        due_date = disbursed_at + dt.timedelta(days=duration)
        diff = timezone.now() - due_date
        return diff.days

    @staticmethod
    def get_loan_status(loan):
        if loan.disbursed_at is not None:
            due_date = loan.disbursed_at + dt.timedelta(days=loan.duration)
            diff = timezone.now() - due_date
            if diff.days == 0:
                status = 'due'
            elif diff.days > 0 and loan.amount_paid < loan.amount_due:
                status = 'overdue'
            else:
                status = loan.status
        else:
            status = loan.status

        if status == "pending":
            status_class = "warning"
        elif status == "approved":
            status_class = 'primary'
        elif status == "disbursed":
            status_class = 'secondary'
        elif status == "overdue":
            status_class = 'danger'
        elif status == "repaid":
            status_class = 'success'
        elif status == "partpayment":
            status_class = 'info'
        else:
            status_class = 'dark'
        return status, status_class

    @staticmethod
    def get_stage(loan):
        if loan.disbursed_at is not None and loan.status in ['disbursed', 'partpayment']:
            due_date = loan.disbursed_at + dt.timedelta(days=loan.duration)
            diff = timezone.now() - due_date
            if diff.days == -1:
                return 'S-1'
            elif diff.days == 0:
                return 'S0'
            elif 1 <= diff.days <= 3:
                return 'S1'
            elif 4 <= diff.days <= 7:
                return 'S2'
            elif 8 <= diff.days <= 15:
                return 'S3'
            elif 16 <= diff.days <= 30:
                return 'S4'
            elif diff.days > 30:
                return 'M1'
        return ''

    @staticmethod
    def get_due_date(loan, fmt='%b %d, %Y'):
        if loan.disbursed_at is not None:
            return f'{(loan.disbursed_at + dt.timedelta(days=loan.duration)):{fmt}}'
        return '-'

    @staticmethod
    def repayment(loan: Loan, amount_paid):
        """
        Run this method after receiving payload, validating transaction, checking for duplicate, etc.
        :param loan:
        :param amount_paid:
        :return:
        """
        amount_paid = float(amount_paid)

        loan.amount_paid += amount_paid
        if loan.amount_paid >= loan.amount_due:
            loan.status = 'repaid'
            loan.repaid_at = timezone.now()
        else:
            loan.status = 'partpayment'
        loan.save()

        if Collection.objects.filter(loan=loan).exists():
            on_collection = Collection.objects.get(loan=loan)
            on_collection.amount_paid = loan.amount_paid
            on_collection.save()
            admin_user = on_collection.user
        else:
            admin_user = AdminUser.objects.filter(level='super admin').first()

        LoanStatic(user=admin_user, loan=loan, status=loan.status).save()
        overdue_days = Func.overdue_days(loan.disbursed_at, loan.duration)
        status = 'repaid' if loan.amount_paid >= loan.amount_due else 'partpayment'
        Timeline(user=admin_user, app_user=loan.user, name='repayment', body=f'Repayment of #{amount_paid:,.2f} was made',
                 detail=loan.status,
                 overdue_days=f'Overdue {overdue_days} Days' if overdue_days > 0 and overdue_days != -1 else 'Due Day').save()

        Repayment(user=loan.user, admin_user=admin_user, loan=loan, principal_amount=loan.principal_amount,
                  amount_due=loan.amount_due, amount_paid_now=amount_paid, total_paid=loan.amount_paid,
                  stage=Func.get_stage(loan), overdue_days=overdue_days, status=status).save()
        Func.eligibility_upgrade(loan.user)

    @staticmethod
    def get_base_amount(level):
        if level == 1:
            level_amount = LEVEL1_BASE_AMOUNT
        elif level == 2:
            level_amount = LEVEL2_BASE_AMOUNT
        elif level == 3:
            level_amount = LEVEL3_BASE_AMOUNT
        else:
            level_amount = LEVEL1_BASE_AMOUNT
        return level_amount

    @staticmethod
    def eligibility_upgrade(user: AppUser):
        overdue_days = [
            repay.overdue_days
            for repay in user.repayment_set.all()
            if not repay.allow
        ]
        max_overdue = max(overdue_days)

        # LEVEL UPGRADE
        if overdue_days.__len__() >= user.borrow_level * 3 and max_overdue <= 0 and user.borrow_level < 2:
            user.borrow_level += 1
            level_amount = Func.get_base_amount(user.borrow_level)
            user.eligible_amount = level_amount

            user.notification_set.create(
                message=f'Congratulations, you reached the premium level! Longer duration, bigger loans',
                message_type='loan_eligibility_update'
            )
        else:
            # USER IS NOT ELIGIBLE TO LEVEL-UPGRADE SO CHECK FOR AMOUNT-UPGRADE
            level_amount = Func.get_base_amount(user.borrow_level)

            if max_overdue <= 3:
                user.eligible_amount += level_amount
                notify = 'Your account is now eligible for bigger loans'
            elif max_overdue <= 5:
                user.eligible_amount += (level_amount/2)
                notify = 'Pay back earlier next time to unlock bigger loans'
            else:
                notify = ''
            if notify != '':
                user.notification_set.create(
                    message=notify,
                    message_type='loan_eligibility_update'
                )
        user.save()

    @staticmethod
    def generate_dummy_loans(start_date, end_date=f'{dt.date.today():%Y-%m-%d}', count_per_day=random.randint(8, 20)):
        start_date = dt.datetime.strptime(start_date, '%Y-%m-%d').date()
        start_date = dt.datetime.combine(start_date, dt.time.min)
        end_date = dt.datetime.strptime(end_date, '%Y-%m-%d').date() + dt.timedelta(days=1)
        end_date = dt.datetime.combine(end_date, dt.time.min)

        current_date = timezone.make_aware(start_date, timezone.get_current_timezone())
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
        total_added = 0
        while current_date <= end_date:
            user_list = [user_obj for user_obj in AppUser.objects.all() if
                         random.randint(1, 10) % 2 == 0 and not Loan.objects.filter(user=user_obj).exists()]
            for no in range(count_per_day):
                user = user_list[no]
                principal_amount = math.ceil(random.randint(3000, 30000) / 1000) * 1000
                amount_disbursed = 0
                amount_due = principal_amount
                amount_paid = 0
                disbursed_at = None
                reloan = random.randint(1, 3)
                status = random.choice(['pending', 'approved', 'disbursed', 'disbursed'])
                if status == 'disbursed' or status == 'repaid':
                    amount_disbursed = (60 / 100) * principal_amount
                    disbursed_at = current_date
                    if status == 'repaid':
                        amount_paid = amount_due
                new_loan = Loan(user=user, principal_amount=principal_amount, amount_disbursed=amount_disbursed,
                                amount_due=amount_due, amount_paid=amount_paid, disbursed_at=disbursed_at,
                                reloan=reloan, status=status, created_at=current_date)
                new_loan.save()
                new_loan.loan_id = f'MGL{new_loan.id}{random.randint(100, 1000)}'
                new_loan.save()
                total_added += 1
            current_date += dt.timedelta(days=1)
        print(f'Success! Loans added: {total_added}')

    @staticmethod
    def generate_random_repayments(count=10):
        loans = Loan.objects.filter(status__in=['disbursed', 'partpayment']).all()
        random_loans = [loan for loan in loans if random.randint(1, 10) in [1, 2, 3]]
        statuses = {'repaid': 0, 'part': 0}
        for loan in random_loans:
            if count > 0:
                count -= 1
                random_status = random.choice(['partpayment', 'repaid', 'repaid', 'repaid'])
                if random_status == 'partpayment':
                    random_perc = math.ceil(random.randint(5, 90) / 4) * 4
                    amount_paid = (random_perc / 100) * (loan.amount_due - loan.amount_paid)
                    statuses['part'] += 1
                else:
                    amount_paid = loan.amount_due - loan.amount_paid
                    statuses['repaid'] += 1
                Func.repayment(loan, amount_paid)

    @staticmethod
    def disburse_loan(admin_user, loans=None):
        """

        :param admin_user: AdminUser object making disbursement
        :param loans: List of loan(s)
        :return:
        """
        # raise 'Disburse function is not yet set'
        bulk_data = [
            {
                'bank_code': loan.user.disbursementaccount.bank_code,
                'account_number': loan.user.disbursementaccount.number,
                'amount': loan.principal_amount - ((loan.interest_perc / 100) * loan.principal_amount),
                'currency': 'NGN',
                'narration': 'MG Loan',
                'reference': f'{loan.loan_id}-{admin_user.id}',
                'meta': [
                    {
                        'email': loan.user.email
                    }
                ]

            }
            for loan in loans
        ]
        # print(bulk_data)
        res = apis.create_bulk_tf(bulk_data, admin_user)
        if res['status'] != 'success':
            print(res)
            return False
        for loan in loans:
            loan.status = 'disbursed'
            loan.amount_disbursed = loan.principal_amount - ((loan.interest_perc / 100) * loan.principal_amount)
            loan.disbursed_at = timezone.now()
            loan.save()
        return True

    @staticmethod
    def set_progressive():
        """
        Must be run at the end of each day
        :return:
        """
        loans = Loan.objects.filter(disbursed_at__gte=timezone.now() - dt.timedelta(days=37))
        daily_loans = loans.annotate(day=TruncDay('disbursed_at')).values('day').annotate(
            total_count=Count(
                Case(
                    When(reloan=1, then='id'),
                    default=Value(None)
                )
            ),
            total_count_reloan=Count(
                Case(
                    When(reloan__gt=1, then='id'),
                    default=Value(None)
                )
            ),
            total_sum=Sum(
                Case(
                    When(reloan=1, then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            total_sum_reloan=Sum(
                Case(
                    When(reloan__gt=1, then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            unpaid_count=Count(
                Case(
                    When((~Q(status='repaid') & Q(reloan=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan=1)),
                         then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            unpaid_count_reloan=Count(
                Case(
                    When((~Q(status='repaid') & Q(reloan__gt=1)) | (
                                Q(amount_paid__lt=F('amount_due')) & Q(reloan__gt=1)), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            unpaid_sum=Sum(
                Case(
                    When((~Q(status='repaid') & Q(reloan=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan=1)),
                         then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            unpaid_sum_reloan=Sum(
                Case(
                    When((~Q(status='repaid') & Q(reloan__gt=1)) | (
                                Q(amount_paid__lt=F('amount_due')) & Q(reloan__gt=1)),
                         then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            )
        ).values('day', 'total_count', 'total_sum', 'unpaid_sum', 'unpaid_count', 'total_count_reloan',
                 'total_sum_reloan', 'unpaid_sum_reloan', 'unpaid_count_reloan')

        # Progressive(disbursed_at=(timezone.now()-dt.timedelta(days=7)).date()).save()
        for day in range(-1, 32):
            for loan in daily_loans:
                if Analysis.is_in_progressive_category(loan['day'], day):
                    current_row, created = Progressive.objects.get_or_create(
                        disbursed_at=timezone.make_aware(dt.datetime.combine(loan['day'].date(), dt.time.min),
                                                         timezone.get_current_timezone()))
                    column = f'day{day}' if day >= 0 else 'a'
                    setattr(current_row, 'total_count', loan['total_count'])
                    setattr(current_row, 'total_sum', loan['total_sum'])
                    setattr(current_row, 'total_count_reloan', loan['total_count_reloan'])
                    setattr(current_row, 'total_sum_reloan', loan['total_sum_reloan'])

                    setattr(current_row, f'{column}_count', loan['unpaid_count'])
                    setattr(current_row, f'{column}_sum', loan['unpaid_sum'])
                    setattr(current_row, f'{column}_count_reloan', loan['unpaid_count_reloan'])
                    setattr(current_row, f'{column}_sum_reloan', loan['unpaid_sum_reloan'])
                    current_row.save()

    @staticmethod
    def set_collectors():
        """
        To be run at the beginning of every day
        Remember that AdminUser must contain at least one staff at each stage who is enabled to collect
        :return:
        """
        # First clear collections
        Func.clear_collections()

        # Start set collections
        exempt_loans = [int(col.loan.id) for col in Collection.objects.all()]
        if exempt_loans:
            loans = Loan.objects.filter(
                Q(disbursed_at__isnull=False) & Q(status='disbursed') & ~Q(pk__in=exempt_loans)).all()
        else:
            loans = Loan.objects.filter(Q(disbursed_at__isnull=False) & Q(status='disbursed')).all()
        stages = ['S-1', 'S0', 'S1', 'S2', 'S3', 'S4', 'M1']
        staged_loans = {}
        for stage in stages:
            staged_loans[stage] = []
            for loan in loans:
                if Analysis.is_in_category(loan.disbursed_at, stage, loan.duration):
                    staged_loans[stage].append(loan)

        # CHECK FOR ACTIVE COLLECTORS AND SHARE AVAILABLE LOANS WITH THEM
        count_per_stage = {stage: int(
            len(staged_loans[stage]) / (AdminUser.objects.filter(level='staff', stage=stage, can_collect=True, status=True).count()))
                           for stage in stages}

        for stage, count in count_per_stage.items():
            loan_index = 0
            for collector in AdminUser.objects.filter(level='staff', stage=stage, can_collect=True, status=True).all():
                assigned_loans = staged_loans[stage][loan_index:loan_index + count]
                loan_index += count
                for loan in assigned_loans:
                    Collection(user=collector, loan=loan, amount_due=loan.amount_due, amount_paid=loan.amount_paid,
                               stage=stage).save()
                    Timeline(user=collector, app_user=loan.user, name='transfer',
                             body=f'Allocated to {collector.stage}-{Func.format_agent_id(collector.stage_id)}',
                             overdue_days=f'Overdue {Func.overdue_days(loan.disbursed_at, loan.duration)} Days').save()

    @staticmethod
    def clear_collections():
        """
        Must be run before set_collectors (this method is called in set_collectors already)
        :return: None
        """
        collections = Collection.objects.all()
        for col in collections:
            if col.stage in ['S-1', 'S0']:
                col.delete()
            else:
                # CLEAR COLLECTIONS AT THE LAST DAY OF EACH STAGE
                if col.stage == 'S1' and Func.overdue_days(col.loan.disbursed_at, col.loan.duration) == 3:
                    col.delete()
                elif col.stage == 'S2' and Func.overdue_days(col.loan.disbursed_at, col.loan.duration) == 7:
                    col.delete()
                elif col.stage == 'S3' and Func.overdue_days(col.loan.disbursed_at, col.loan.duration) == 15:
                    col.delete()
                elif col.stage == 'S4' and Func.overdue_days(col.loan.disbursed_at, col.loan.duration) == 30:
                    col.delete()

    @staticmethod
    def set_recovery():
        """
        This method must be run at the beginning of each day immediately after set_collection,
        and also at the end of each day (roughly same time as set_progressive)
        :return:
        """
        # Sort needed fields from collection by user
        cols = (Collection.objects.values('user').annotate(
            total_count=Count('id'),
            amount_held=Sum(
                F('amount_due') - F('amount_paid'),
                output_field=django.db.models.FloatField()
            ),
            paid_count=Count('id', filter=Q(amount_paid__gte=F('amount_due')))
        ).annotate(
            amount_paid=Sum(
                F('amount_paid'),
                output_field=django.db.models.FloatField()
            ),
        ).values('user', 'total_count', 'amount_held', 'amount_paid', 'paid_count'))
        results = {
            AdminUser.objects.get(pk=col['user']): {
                'total_count': col['total_count'],
                'amount_held': col['amount_held'],
                'amount_paid': col['amount_paid'],
                'paid_count': col['paid_count']
            }
            for col in cols
        }

        # if method was run in the beginning of the day, create new objects for collectors
        if dt.datetime.now().hour == 0:
            for user, details in results.items():
                Recovery(
                    user=user,
                    total_count=details['total_count'],
                    amount_held=details['amount_held'],
                    amount_paid=details['amount_paid'],
                    paid_count=details['paid_count']
                ).save()
            remaining_staff = AdminUser.objects.filter(~Q(pk__in=[col['user'] for col in cols]) & Q(level='staff')).all()
            for staff in remaining_staff:
                Recovery(user=staff).save()  # add staff to recovery with default values of 0
        else:
            # if run at the end of the day, get and update records made at the beginning of same day
            today_recovery = Recovery.objects.filter(created_at__date=dt.date.today())
            today_collectors = {recovery.user: recovery for recovery in today_recovery}
            for user, details in results.items():
                if user in today_collectors.keys():
                    recovery = today_collectors[user]
                    recovery.amount_paid = details['amount_paid'] - recovery.amount_paid
                    recovery.paid_count = details['paid_count'] - recovery.paid_count
                    recovery.total_count = details['total_count']
                    recovery.rate = (recovery.paid_count / recovery.total_count) * 100
                    recovery.save()
                else:
                    Recovery(
                        user=user,
                        total_count=details['total_count'],
                        amount_held=details['amount_held'],
                        amount_paid=details['amount_paid'],
                        paid_count=details['paid_count'],
                        rate=(details['paid_count']/details['total_count']) * 100
                    ).save()

    @staticmethod
    def generate_dummy_sms(user_phone, count, start_date=(dt.date.today()-dt.timedelta(days=2)).strftime('%Y-%m-%d')):
        """
        This method only creates a conversation.
        You may have to run this method multiple times to create various conversations, according to your need.
        :param user_phone: Customer's phone
        :param count: How many messages you want to create in this conversation
        :param start_date: When to start dating this conversation
        :return:
        """
        user = AppUser.objects.get(phone=user_phone)
        fake = Faker()
        phone = fake.phone_number()
        name = fake.name()
        start_date = dt.datetime.strptime(start_date, '%Y-%m-%d')
        for _ in range(count):
            date = start_date + dt.timedelta(hours=2)
            fake = Faker()
            SmsLog(
                user=user,
                name=name,
                phone=phone,
                message=" ".join(fake.sentences(random.randint(1, 4))),
                category=random.choice(['incoming', 'outgoing']),
                date=date
            ).save()

    @staticmethod
    def generate_dummy_contacts(user_phone, count):
        user = AppUser.objects.get(phone=user_phone)
        for _ in range(count):
            fake = Faker()
            Contact(
                user=user,
                name=fake.name(),
                phone=fake.phone_number(),
                category=''
            ).save()

    @staticmethod
    def update_blacklist():
        """
        This method will be run at the beginning of each day (or end of day, as manager wishes).
        It checks for all first day overdue loans and goes on to blacklist the users
        :return:
        """
        loans = Loan.objects.filter(status='disbursed')
        for loan in loans:
            loan_status, _ = Func.get_loan_status(loan)
            if Func.overdue_days(loan.disbursed_at, loan.duration) == 1 and loan.status != 'repaid':
                Blacklist(user=loan.user).save()

    @staticmethod
    def webhook(event, data):
        if event == 'charge.completed':
            return Func.webhook_charge(data)
        elif event == 'transfer.completed':
            return Func.webhook_transfer(data)

    @staticmethod
    def webhook_charge(data):
        if apis.is_tx_valid(data['id']):
            if not Repayment.objects.filter(tx_id=data['id']).exists():
                user = AppUser.objects.get(phone=data['customer']['phone_number'])
                if user:
                    loan = user.loan_set.last()
                    Func.repayment(loan=loan, amount_paid=data['amount'])
                    Logs(action='credit',
                         body=f'Credit of #{data["amount"]:,} from {data["customer"]["name"]}',
                         status='success', fee=float(data['app_fee'])).save()
                    return True
        return False

    @staticmethod
    def webhook_transfer(data):
        tx_id = data['id']
        loan_id = data['reference'].split('-')[0]
        admin_id = data['reference'].split('-')[1]
        loan = Loan.objects.get(loan_id=loan_id)
        admin = AdminUser.objects.get(pk=admin_id)
        if loan:
            if data['status'] == 'SUCCESSFUL':
                loan.disburse_id = tx_id
                loan.save()
                Timeline(user=admin, app_user=loan.user, name='disbursement',
                         body=f'Loan of &#x20A6;{loan.principal_amount} was requested. &#x20A6;{loan.amount_disbursed} was disbursed').save()
                LoanStatic(user=admin, loan=loan, status='disbursed').save()
                Logs(action='transfer', body=f'Transfer of #{data["amount"]:,} to {data["account_number"]}, {data["bank_name"]} - {data["fullname"]} was successful', status='success', fee=float(data['fee'])).save()
            else:
                loan.status = 'approved'
                loan.amount_disbursed = 0
                loan.disbursed_at = None
                loan.save()
                Logs(action='transfer',
                     body=f'Failed to transfer #{data["amount"]:,} to {data["account_number"]}, {data["bank_name"]} - {data["fullname"]}.',
                     status='danger').save()
        return True

    @staticmethod
    def is_eligible(user: AppUser, amount):
        if AcceptedUser.objects.filter(phone=user.phone).exists():
            Func.system_whitelist(user)
            if not user.is_blacklisted():
                if amount <= user.eligible_amount:
                    if not Loan.objects.filter(Q(user=user) & ~Q(status__in=['repaid', 'declined'])):
                        if user.contact_set.count() >= 200:
                            if Func.sms_count(user) >= 30:
                                return True, f'Eligible - User can borrow up to &#x20A6;{user.eligible_amount:,}'
                            return False, 'Ineligible - User SMS < 30'
                        return False, 'Ineligible - User contacts < 1000'
                    return False, 'User has an outstanding loan'
                return False, f'User can only loan up to N{user.eligible_amount:,}'
            return False, 'Ineligible - User was blacklisted by system'
        return False, 'Ineligible - User is not on filtered list'

    @staticmethod
    def system_blacklist(user: AppUser):
        if user.is_blacklisted():
            ub = Blacklist.objects.get(user=user)
            if ub.expires_at:
                ub.expires_at = timezone.now() + dt.timedelta(days=10)
        else:
            Blacklist(user=user, expires_at=timezone.now() + dt.timedelta(days=10)).save()

    @staticmethod
    def system_whitelist(user: AppUser):
        if user.is_blacklisted():
            if getattr(user, 'blacklist').expires_at and getattr(user, 'blacklist').expires_at < timezone.now():
                getattr(user, 'blacklist').delete()

    @staticmethod
    def sms_count(user: AppUser):
        sms = user.smslog_set.values('phone').annotate(sms_count=Count('id')).values('sms_count', 'phone')
        return len(sms)


class UserUtils:
    def __init__(self, request, **kwargs):
        self.user, self.users, self.user_id, self._content, self._content2 = None, None, None, None, None
        self.avatar = ''
        self.kwargs = kwargs
        self.action = self.kwargs['action']
        self.request = request
        self._status, self._message = 'success', 'success'

    def fetch_users_in_table(self,
                             rows=10,
                             start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                             end=f'{dt.date.today():%Y-%m-%d}',
                             filters=''
                             ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        self.users = AppUser.objects.filter(
                (
                        Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
                )
                &
                (
                        Q(user_id__startswith=filters) | Q(phone__startswith=filters) |
                        Q(bvn__startswith=filters) | Q(first_name__startswith=filters) |
                        Q(last_name__startswith=filters)
                )
            ).order_by('-created_at').all()
        self._content = ''
        rows = int(rows)
        for self.user in self.users:
            if rows > 0:
                avatar = '/static/admin_panel/images/avatars/user.png' if not hasattr(self.user, 'avatar') else f'https://loanproject.fra1.digitaloceanspaces.com/user_docs/{self.user.avatar.name}'

                self.add_table_content(_for='all_users_table', avatar=avatar)
                rows -= 1

    def fetch_other_details(self):
        self._content = {}
        self._content['bankdetails_number'] = self.user.disbursementaccount.number
        self._content['bankdetails_bank'] = self.user.disbursementaccount.bank_name
        self._content['bankdetails_name'] = f'{self.user.last_name} {self.user.first_name}'
        self._content['bankdetails_bvn'] = self.user.bvn

        self._content['virtual_bankdetails_number'] = self.user.virtualaccount_set.last().number
        self._content['virtual_bankdetails_bank'] = self.user.virtualaccount_set.last().bank_name
        self._content['virtual_bankdetails_name'] = f'{self.user.last_name} {self.user.first_name}'

        self._content['loan_count'] = self.user.loan_set.count()
        self._content['repayment_count'] = self.user.repayment_set.count()
        self._content['notes_count'] = self.user.note_set.count()
        self._content['files_count'] = self.user.document_set.count()+1 if hasattr(self.user, 'avatar') else self.user.document_set.count()
        self.fetch_notes_in_table()
        self._content['tables'] = {'notes': self._content2}
        self.fetch_files_in_table()
        self._content['tables']['files'] = self._content2

        # Prepare data for overdue days chart
        data_y = []
        data_x = []
        for rep in self.user.repayment_set.filter(loan__status='repaid'):
            data_y.append(rep.overdue_days)
            data_x.append(f'{rep.created_at:%b %d}')
        self._content['overdue_chart'] = {
            'x': data_x,
            'y': data_y
        }
        self._content['max_overdue_days'] = sorted(data_y)[len(data_y)-1] if data_y else '-'

    def fetch_notes_in_table(self):
        self._content2 = ''
        for note in self.user.note_set.all().order_by('-id'):
            modified = ''
            if note.modified:
                modified = f"📢 modified- {note.modified_at:%d/%m/%y}"
            self.add_table_content(_for='note', note=note, modified=modified)

    def delete_note(self):
        note = Note.objects.get(pk=self.kwargs['note_id'])
        if not note.super and self.request.user.level in ['super admin', 'team leader', 'admin']:
            action = f'Deleted note: ({note.body[:18]}...)'
            AdminUtils.log(user=self.request.user, app_user=self.user, action_type='delete_note', action=action)
            note.delete()
            self._message = 'Note deleted successfully'
        else:
            self._message = 'Comment cannot be deleted'
            self._status = 'info'
        self.fetch_notes_in_table()
        self._content = self._content2

    def add_note(self):
        note = Note(user=self.request.user, app_user=self.user, body=self.kwargs['note'], super=self.kwargs.get('super') or False)
        if self.user.loan_set.last():
            overdue_days = f'Overdue {Func.overdue_days(self.user.loan_set.last().disbursed_at, self.user.loan_set.last().duration)} Days' if self.user.loan_set.last().status in ('disbursed', 'partpayment') else 'Loan Inactive'
        else:
            overdue_days = 'Loan Inactive'
        Timeline(user=self.request.user,
                 app_user=self.user,
                 name='collection record',
                 body=self.kwargs['note'],
                 overdue_days=overdue_days
                 ).save()
        action = f'Added note: ({note.body[:15]}...)'
        AdminUtils.log(user=self.request.user, app_user=self.user, action_type='add_note', action=action)
        note.save()
        self._message = 'Note added successfully!'
        self.fetch_notes_in_table()
        self._content = self._content2

    def modify_note(self):
        note = Note.objects.get(pk=self.kwargs['note_id'])
        if note.body != self.kwargs['note'] and not note.super:
            action = f'Modified note: ({note.body[:15]}...)'
            AdminUtils.log(user=self.request.user, app_user=self.user, action_type='add_note', action=action)
            note.body = self.kwargs['note']
            note.modified = timezone.now()
            note.modified = True
            note.save()
            self._message = 'Note modified successfully'
        else:
            self._message = 'Nothing changed'
            self._status = 'info'

    def fetch_files_in_table(self):
        self._content2 = ''
        if hasattr(self.user, 'avatar'):
            self.add_table_content(_for='file', file=self.user.avatar)
        for file in self.user.document_set.all():
            self.add_table_content(_for='file', file=file)

    def update_user(self):
        if self.request.user.level in ('super admin', 'admin'):
            amount_fields = ['eligible_amount']
            key = self.kwargs['key']
            value = self.kwargs['value']
            if key in amount_fields:
                value = float(value.replace(',', ''))
            if value == getattr(self.user, key):
                self._message = 'No changes was made'
                self._status = 'info'
                return None
            log_detail = f"Updated user's {key} from {getattr(self.user, key)} to {value}"

            setattr(self.user, key, value)
            self.user.save()
            AdminUtils.log(self.request.user, app_user=self.user, action_type='profile update', action=log_detail)
            self._message = f'{key} updated successfully'
        else:
            self._message = 'No permission'
            self._status = 'error'
            return None

    def delete_user(self):
        self.user.delete()
        self._message = 'User deleted successfully'
        self._status = 'success'

    def doc_decide(self):
        if self.request.user.level in ('super admin', 'admin'):
            if self.kwargs['doc_action'] == 'approve':
                self.user.status = True
                status = 'success'
            else:
                self.user.status = False
                self.user.status_reason = self.kwargs['doc_reason']
                status = 'danger'
            self.user.save()
            self._message = f'Docs {self.kwargs["doc_action"]}d for user'
            self._status = 'success'
            self._content = f"""User Docs  <span class="badge text-bg-{status}">{self.kwargs['doc_action'].upper()}D</span>"""
        else:
            self._message = f'No such permission. Please contact admin'
            self._status = 'danger'
            self._content = f"""User Docs  <span class="badge text-bg-{'success' if self.user.status else 'danger'}">STATUS</span>"""
        self._content = {'doc_status': self.user.status, 'doc_reason': self.user.status_reason, 'html': self._content}

    def check_eligibility(self):
        is_eligible, reason = Func.is_eligible(self.user, self.user.eligible_amount)
        if is_eligible:
            self._status = 'success'
        else:
            self._status = 'error'
        self._message = reason

    def blacklist(self):
        if hasattr(self.user, 'blacklist'):
            self.user.blacklist.delete()
            self._message = 'User whitelisted'
        else:
            Blacklist(user=self.user).save()
            self._message = 'User blacklisted'

    def fetch_blacklist(self,
                        rows=10,
                        start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                        end=f'{dt.date.today():%Y-%m-%d}',
                        filters=''
                        ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        items = Blacklist.objects.filter(
            (
                    Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
            )
            &
            (
                    Q(user__user_id__startswith=filters) | Q(user__phone__startswith=filters) |
                    Q(user__bvn__startswith=filters) | Q(user__first_name__startswith=filters) |
                    Q(user__last_name__startswith=filters)
            )
        ).order_by('-created_at').all()
        self._content = ''
        rows = int(rows)
        for item in items:
            if rows > 0:
                self.add_table_content(_for='blacklist', row=item)
                rows -= 1

    def get_timeline(self):
        timelines = Timeline.objects.filter(app_user=self.user).order_by('-created_at').all()
        self._content2 = ''
        for tl in timelines:
            self.add_table_content(_for='timeline', tl=tl)
        self._content = self._content2

    @staticmethod
    def reverse_dict(it: dict):
        return {a: b for a, b in reversed(it.items())}

    def fetch_sms(self, which):
        self.user: AppUser
        logs = self.user.smslog_set.order_by('date').all()
        if logs:
            logs_dict = {}
            for log in logs:
                if log.phone not in logs_dict.keys():
                    logs_dict[log.phone] = [log]
                else:
                    logs_dict[log.phone].append(log)

            content = {}
            if which == 'sidebar':
                self._content = ''
                logs_dict = UserUtils.reverse_dict(logs_dict)
                for phone, logs_list in logs_dict.items():
                    last_log = logs_list[len(logs_list)-1]
                    self.add_table_content(_for='sms_sidebar', log=last_log)
                content['sidebar'] = self._content
                content['content'] = """
                    <div style="justify-content: center; height: 100%; align-items: center; display: flex;">
                        <i>Click on a conversation to view...</i>
                    </div>
                """
            else:
                self._content = ''
                logs_list = logs_dict[which]

                for log in logs_list:
                    self.add_table_content(_for='sms_content', log=log)
                content['content'] = self._content
                last_log = logs_list[len(logs_list)-1]
                content['last_updated'] = f'{last_log.created_at:%b %d, %I:%M %p}'
                content['name'] = last_log.name
                content['phone'] = last_log.phone
            self._content = content
            self._status = 'success'
        else:
            self._content = {
                'sidebar': """
                    <a href="javascript:;" class="list-group-item active">
						<div class="d-flex">
							<div class="flex-grow-1 ms-2">
								<h6 class="mb-0 chat-title">No Data</h6>
								<p class="mb-0 chat-msg">No conversations here yet..</p>
							</div>
							<div class="chat-time"></div>
						</div>
					</a>
                """,
                'content': """
                    <div style="justify-content: center; height: 100%; align-items: center; display: flex;">
                        <i>Click on a conversation to view...</i>
                    </div>
                """
            }
            self._status = 'error'
            self._message = 'No data available'

    def fetch_contact(self):
        self.user: AppUser
        contacts = self.user.contact_set.order_by('name').all()
        content = {}
        self._content = ''
        if contacts:
            for contact in contacts:
                self.add_table_content(_for='contact', contact=contact)
            content['sidebar'] = self._content
        else:
            content['sidebar'] = """
                    <a href="javascript:;" class="list-group-item active">
						<div class="d-flex">
							<div class="flex-grow-1 ms-2">
								<h6 class="mb-0 chat-title">No Data</h6>
								<p class="mb-0 chat-msg">No contacts here yet..</p>
							</div>
							<div class="chat-time"></div>
						</div>
					</a>
                """
        content['content'] = """
                    <div style="justify-content: center; height: 100%; align-items: center; display: flex;">
                        <i>Nothing to show here...</i>
                    </div>
                """
        self._content = content

    def fetch_call(self):
        self.user: AppUser
        calls = self.user.calllog_set.order_by('-date').all()
        content = {}
        self._content = ''
        if calls:
            for call in calls:
                self.add_table_content(_for='call', call=call)
            content['sidebar'] = self._content

            # Get Data For Call Chart
            sorted_calls = self.user.calllog_set.values('phone').annotate(
                count=Count('phone')
            ).order_by('-count')[:10]
            phones, count = [], []
            for call in sorted_calls:
                phones.append(call['phone'])
                count.append(call['count'])
            # phones.reverse()
            # count.reverse()
            content['chart_phones'] = phones
            content['chart_count'] = count
        else:
            content['sidebar'] = """
                            <a href="javascript:;" class="list-group-item active">
        						<div class="d-flex">
        							<div class="flex-grow-1 ms-2">
        								<h6 class="mb-0 chat-title">No Data</h6>
        								<p class="mb-0 chat-msg">No calls here yet..</p>
        							</div>
        							<div class="chat-time"></div>
        						</div>
        					</a>
                        """
        content['content'] = """
                        <div style="justify-content: center; height: 100%; align-items: center; display: flex;" id="call-chart">
                            
                        </div>
                """
        self._content = content

    def process(self):
        if self.action == "get_all_users":
            self.fetch_users_in_table(
                rows=self.kwargs.get('rows', 10),
                start=self.kwargs.get('start'),
                end=self.kwargs.get('end'),
                filters=self.kwargs.get('filters')
            )
        elif self.action == 'fetch_blacklist':
            self.fetch_blacklist(
                rows=self.kwargs.get('rows', 10),
                start=self.kwargs.get('start'),
                end=self.kwargs.get('end'),
                filters=self.kwargs.get('filters')
            )
        else:
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            if self.action == "get_other_details":
                self.fetch_other_details()
            elif self.action == "update_user":
                self.update_user()
                self.content = self.message
            elif self.action == "delete_note":
                self.delete_note()
            elif self.action == "add_note":
                self.add_note()
            elif self.action == "modify_note":
                self.modify_note()
            elif self.action == "fetch_files":
                self.fetch_files_in_table()
            elif self.action == "get_timeline":
                self.get_timeline()
            elif self.action == 'fetch_sms':
                self.fetch_sms(self.kwargs['which'])
            elif self.action == 'fetch_contact':
                self.fetch_contact()
            elif self.action == 'blacklist':
                self.blacklist()
            elif self.action == 'doc_decide':
                self.doc_decide()
            elif self.action == 'check_eligibility':
                self.check_eligibility()
            elif self.action == 'delete_user':
                self.delete_user()
            elif self.action == 'fetch_call':
                self.fetch_call()

    def add_table_content(self, _for='', **kwargs):
        if _for == 'all_users_table':
            self._content += f"""
                                <tr 
                                    data-user_id='{self.user.user_id}' 
                                    data-first_name='{self.user.first_name}' 
                                    data-eligible_amount='{self.user.eligible_amount:,}' 
                                    data-last_name='{self.user.last_name}' 
                                    data-phone='{self.user.phone}' 
                                    data-phone2='{self.user.phone2}' 
                                    data-middle_name='{self.user.middle_name}' 
                                    data-email='{self.user.email}' 
                                    data-gender='{self.user.gender}' 
                                    data-state='{self.user.state}' 
                                    data-lga='{self.user.lga}' 
                                    data-email2='{self.user.email2}' 
                                    data-address='{self.user.address}' 
                                    data-dob='{self.user.dob}' 
                                    data-created_at="{self.user.created_at:%a %b %d, %Y}" 
                                    data-avatar="{kwargs['avatar']}" 
                                    data-doc_status="{self.user.status}"
                                    data-doc_reason="{self.user.status_reason}"
                                    data-status='{'Active' if not self.user.is_blacklisted() else f'Blacklisted: {getattr(self.user, "blacklist").created_at:%b %d}'}' 
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if not self.user.is_blacklisted() else 'danger'}">{'Active' if not self.user.is_blacklisted() else f'Blacklisted: {getattr(self.user, "blacklist").created_at:%b %d}'}</span>' 
                                    data-style='grey' 
                                    data-last_access='{self.user.last_access}' class='user_rows' data-bs-toggle='modal' data-bs-target='#exampleLargeModal1'>

                                    <td>
                                		<div class='d-flex align-items-center'>
                                		<div class="user-presence user-{'online' if not self.user.is_blacklisted() else 'offline'}" data-user_id="{self.user.user_id}">
                                			<img src="{kwargs['avatar']}" width="10" height="10" alt="" class="rounded-circle"></div>
                                		</div>
                                	</td>

                                	<td>{self.user.user_id}</td>
                                	<td>{self.user.last_name} {self.user.first_name}</td>
                                	<td>{self.user.phone}</td>
                                	<td>{self.user.email}</td>
                                	<td>{self.user.created_at:%a %b %d, %Y}</td>
                                	<td>{self.user.address}</td>
                                	<td>{self.user.last_access:%a %b %d, %Y}</td>	
                                </tr>
                            """

        elif _for == 'note':
            note = kwargs['note']
            self._content2 += f"""
                        <div class="col-12">
                            <div id="todo-container">
                                    <div class="pb-3 todo-item">
                                        <div class="input-group">

                                            <div class="input-group-text">
                                                <input type="checkbox" aria-label="Checkbox for following text input" data-id="{note.id}" disabled class="task-status">
                                            </div>

                                            <textarea data-id="{note.id}" class="form-control old_note" rows=2>{note.body}</textarea>

                                            <button class="btn btn-outline-secondary bg-danger text-white delete_note" data-id="{note.id}" type="button">X</button>
                                            <div style="width: 100%; display: inine-block; background: #E9ECEF" >
                                            <span style="float: left; width: 40%" class="px-2"> By: S{note.user.stage}-{Func.format_agent_id(note.user.stage_id)}
                                            </span>
                                            <span style="float: right; width: 40%; text-align: right" class="px-2">-{note.created_at:%a %d %b, %Y @ %I:%M %p} <span style="font-weight: bold" class="text-primary">{kwargs['modified']}</span>
                                            </span>
                                            </div>

                                        </div>
                                </div>
                            </div>
                        </div>
                        """

        elif _for == 'file':
            file: Document = kwargs['file']
            self._content2 += f"""
                <div class="row my-4">
            		<div class="col-md-9">
            			<input type="text" class="form-control" value="{file.description.upper()}: {file.name.rsplit('.')[-1].upper()}" disabled style="width: 100%; border-right: none">
            		</div>
            		<div class="col-md-3 text-end d-grid">
            			<a href="https://loanproject.fra1.digitaloceanspaces.com/user_docs/{file.name}" target='_blank'><button class="btn btn-primary">Download <i class="bx bx-right-top-arrow-circle"></i></button></a>
            		</div>
            		<img style="width: 40%" src="https://loanproject.fra1.digitaloceanspaces.com/user_docs/{file.name}">
            	</div>
            """

        elif _for == 'sms_sidebar':
            log = kwargs['log']
            self._content += f"""
                <a href="javascript:;" class="list-group-item sms_sidebar_item phonebook_item" data-name="{log.name}" data-message="{log.message}" data-phone="{log.phone}">
					<div class="d-flex">
						<div class="chat-user-offline">
							<img src="/static/admin_panel/images/avatars/user.png" width="42" height="42" class="rounded-circle" alt="">
						</div>
						<div class="flex-grow-1 ms-2">
							<h6 class="mb-0 chat-title">{log.name}</h6>
							<p class="mb-0 chat-msg">{log.message if len(log.message) < 15 else f'{log.message[:15]}...'}</p>
						</div>
						<div class="chat-time">{log.date:%b %d, %I:%M %p}</div>
					</div>
				</a>
            """

        elif _for == 'sms_content':
            log = kwargs['log']
            if log.category == 'incoming':
                self._content += f"""
                    <div class="chat-content-leftside">
							<div class="d-flex">
								<img src="/static/admin_panel/images/avatars/user.png" width="30" height="30" class="rounded-circle" alt="">
								<div class="flex-grow-1 ms-2">
									<p class="mb-0 chat-time">{log.name}, {log.date:%b %d, %I:%M %p}</p>
									<p class="chat-left-msg">{log.message}</p>
								</div>
							</div>
						</div>
                """
            else:
                self._content += f"""
                    <div class="chat-content-rightside">
							<div class="d-flex ms-auto">
								<div class="flex-grow-1 me-2">
									<p class="mb-0 chat-time text-end">Customer, {log.date:%b %d, %I:%M %p}</p>
									<p class="chat-right-msg">{log.message}</p>
								</div>
							</div>
						</div>
                """

        elif _for == 'contact':
            contact = kwargs['contact']
            self._content += f"""
                            <a href="javascript:;" class="list-group-item contact_item phonebook_item" data-name="{contact.name}" data-message="" data-phone="{contact.phone}">
            					<div class="d-flex">
            						<div class="chat-user-offline">
            							<img src="/static/admin_panel/images/avatars/user.png" width="42" height="42" class="rounded-circle" alt="">
            						</div>
            						<div class="flex-grow-1 ms-2">
            							<h6 class="mb-0 chat-title">{contact.name}</h6>
            							<p class="mb-0 chat-msg" >{contact.phone}</p>
            						</div>
            						<div class="chat-time"><span class='badge text-bg-primary' onclick="copy_to_clipboard('{contact.phone}')"><i class='bx bx-copy'></i> copy</span></div>
            					</div>
            				</a>
                        """

        elif _for == 'call':
            call = kwargs['call']
            if call.category == 'incoming':
                call_class = 'primary'
                icon = 'phone-incoming'
            elif call.category == 'outgoing':
                call_class = 'primary'
                icon = 'phone-outgoing'
            elif call.category == 'missed':
                call_class = 'danger'
                icon = 'phone-incoming'
            elif call.category == 'rejected':
                call_class = 'danger'
                icon = 'block'
            elif call.category == 'blocked':
                call_class = 'danger'
                icon = 'block'
            else:
                call_class = 'info'
                icon = 'phone'

            self._content += f"""
                            <a href="javascript:;" class="list-group-item contact_item phonebook_item" data-name="{call.name}" data-message="" data-phone="{call.phone}">
            					<div class="d-flex">
            						<div class="chat-user-offline">
            							<img src="/static/admin_panel/images/avatars/user.png" width="42" height="42" class="rounded-circle" alt="">
            						</div>
            						<div class="flex-grow-1 ms-2">
            							<h6 class="mb-0 chat-title fw-bold text-{call_class}">{'Unsaved' if call.name == '' else call.name} <i class='bx bx-{icon} text-{call_class}'></i></h6>
            							<p class="mb-0 chat-msg" >{call.phone}</p>
            						</div>
            						<div class="chat-time"><span class='badge text-bg-primary' onclick="copy_to_clipboard('{call.phone}')"><i class='bx bx-copy'></i> copy</span></div>
            					</div>
            				</a>
                        """

        elif _for == 'call_content':
            self._content = """
            <div style="justify-content: center; height: 100%; align-items: center; display: flex;">
                <i>Nothing to show here...</i>
            </div>
            """

        elif _for == 'timeline':
            tl: Timeline = kwargs['tl']
            detail = ''
            body = ''
            overdue_class = 'dark' if tl.overdue_days == 'Loan Inactive' else 'danger'
            overdue = f'<span class="badge text-bg-{overdue_class}">{tl.overdue_days}</span>'
            if tl.name == 'transfer':
                body = f'Allocated to {tl.user.stage}-{Func.format_agent_id(tl.user.stage_id)}'
            elif tl.name == 'repayment':
                detail = f"""<span class="badge text-bg-{'warning' if tl.detail == 'partpayment' else 'success'}">{tl.detail.title()}</span>"""
                body = tl.body
            elif tl.name == "collection record":
                body = tl.body
            elif tl.name == "disbursement":
                body = tl.body
                overdue = ''
            elif tl.name == "manual assign":
                body = tl.body
            self._content2 += f"""
                <li class="timeline-item" data-name='{tl.name}'>
                    <div class="timeline-content">
                        <div class="d-flex justify-content-between align-items-center">
                            <div>
                                <strong>{tl.created_at:%d-%m-%Y}</strong><br>
                                <small>{tl.created_at:%H:%M:%S}</small>
                            </div>
                            <div class="badge rounded-pill text-bg-info">{tl.name.title()}</div>
                        </div>
                        <div class="mt-2">
                            {overdue}
                            <span class="badge text-bg-primary">{tl.user.stage}-{Func.format_agent_id(tl.user.stage_id)}</span>
                            {detail}
                        </div>
                        <div class="mt-1">{body}</div>
                    </div>
                </li>
            """

        elif _for == 'blacklist':
            row = kwargs['row']
            self._content += f"""
                <tr>
                    <td>{row.user.user_id}</td>
                    <td>{row.user.last_name} {row.user.first_name}</td>
                    <td>{row.user.phone}</td>
                    <td>{row.user.email}</td>
                    <td>{row.created_at:%a %b %d, %Y}</td>
                    <td><a href="#0" class="blacklist" data-user_id="{row.user.user_id}">Whitelist</a></td>
                    
                </tr>
                
            """

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        self._content = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value

    @property
    def content2(self):
        return self._content2

    @content2.setter
    def content2(self, value):
        self._content2 = value


class AdminUtils:
    def __init__(self, request, **kwargs):
        self.admin_user: AdminUser = request.user
        self.kwargs = kwargs
        self._status, self._message, self._content = 'success', 'success', None
        self.action = kwargs['action']

    @staticmethod
    def log(user: AdminUser, app_user: AppUser, action_type='', action=''):
        AdminLog(user=user, app_user=app_user, action_type=action_type, action=action).save()

    def fetch_assigned(self, loan):
        collectors = AdminUser.objects.filter(level='staff').annotate(
            sort_index=Case(
                When(stage='S-1', then=1),
                When(stage='S0', then=2),
                When(stage='S1', then=3),
                When(stage='S2', then=4),
                When(stage='S3', then=5),
                When(stage='S4', then=6),
                When(stage='M1', then=7),
                output_field=django.db.models.IntegerField()
            )
        ).order_by('sort_index').all()
        self._content = ''
        for collector in collectors:
            checked = ''
            avail = ''
            count = len(collector.collection_set.all())
            if Collection.objects.filter(loan=loan).exists() and Collection.objects.get(
                    loan=loan) in collector.collection_set.all():
                checked = 'checked'
            if collector.level == "team leader":
                avail = "disabled"
                count = f"All {collector.stage}"
                checked = 'checked'
            self._content += f"""
                        <tr class='agents_trs'>
                		    <td>{collector.stage}-{Func.format_agent_id(collector.stage_id)}</td>
                		    <td>{count}</td>
                		    <td>
                		    <div _ngcontent-bfo-c214='' class='form-check form-switch'><input _ngcontent-bfo-c214='' type='checkbox' id='flexSwitchCheckChecked' {checked} {avail} class='form-check-input assign_check' data-collector_id='{collector.id}' style='cursor:pointer;'></div>
                			</td>
                		</tr>
                        """

    def assign(self, loan: Loan, action, collector: AdminUser):
        if action == "add":
            if Collection.objects.filter(loan=loan).exists():
                self._status = 'error'
                self._message = 'Loan already assigned. Please de-assign to complete action'
                return
            # Assign
            Collection(user=collector, loan=loan, amount_due=loan.amount_due, amount_paid=loan.amount_paid,
                       stage=Func.get_stage(loan)).save()
            overdue_days = Func.overdue_days(loan.disbursed_at, loan.duration) if loan.disbursed_at else '-'
            Timeline(user=collector, app_user=loan.user, name='manual assign',
                     body=f'Allocated to {collector.stage}-{Func.format_agent_id(collector.stage_id)}',
                     overdue_days=f'Overdue {overdue_days} Days' if overdue_days != '-' and overdue_days > 0 else f'{overdue_days} Due Day').save()
            self._status = 'success'
            self._message = 'Assigned successfully'
        elif action == 'remove':
            if not Collection.objects.filter(loan=loan).exists():
                self._status = 'error'
                self._message = 'Loan is not assigned. Reload selection'
                return
            Collection.objects.filter(loan=loan).delete()
            self._status = 'success'
            self._message = 'Un-assigned successfully'

        self.fetch_assigned(loan)

    def fetch_operators(self):
        stage = self.kwargs['stage'].split(',')
        agents = AdminUser.objects.filter(stage__in=stage).annotate(
            sort_index=Case(
                When(stage='S-1', then=0),
                When(stage='S0', then=2),
                When(stage='S1', then=3),
                When(stage='S2', then=4),
                When(stage='S3', then=5),
                When(stage='S4', then=6),
                When(stage='M1', then=7),
                output_field=django.db.models.IntegerField()
            )
        ).order_by('sort_index').all()

        recs = Recovery.objects.values('user').annotate(
            total_rate=Sum('rate'),
            total_count=Count('id')
        ).values('user', 'total_rate', 'total_count')

        recoverys = {
            AdminUser.objects.get(pk=rec['user']): (rec['total_rate'] / (100*rec['total_count']))*100
            for rec in recs
        }

        sn = 0
        self._content = ''
        for agent in agents:
            sn += 1
            self.add_table_content(_for='operators', sn=sn, agent=agent, recovery=int(recoverys[agent]) if agent in recoverys.keys() else '')

    def fetch_logs(self,
                        rows=10,
                        start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                        end=f'{dt.date.today():%Y-%m-%d}',
                        filters=''
                        ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        logs = Logs.objects.filter(
            (
                    Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
            )
            &
            (
                    Q(action__startswith=filters) | Q(body__startswith=filters) |
                    Q(status__startswith=filters)
            )
        ).order_by('-created_at').all()
        self._content = ''
        rows = int(rows)
        for log in logs:
            if rows > 0:
                self.add_table_content(_for='logs', row=log)
                rows -= 1

    def operator_details(self):
        operator = AdminUser.objects.get(pk=self.kwargs['id'])
        if operator.level != 'staff':
            return
        collections = Collection.objects.filter(user=operator).all()

        response = {}
        self._content = ''
        for col in collections:
            self.add_table_content(_for='operator_loans', col=col)
        response['loans'] = self._content

        repayments = Repayment.objects.filter(admin_user=operator).all()
        self._content = ''
        for repay in repayments:
            self.add_table_content(_for='operator_repayments', repay=repay)

        cols = Collection.objects.filter(user=operator).values('user').annotate(
            total_count=Count('id'),
            total_held=Sum(
                F('amount_due'),
                output_field=django.db.models.FloatField()
            ),
            new_count=Count(
                Case(
                    When(created_at__date=dt.date.today(), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            paid_sum=Sum(
                Case(
                    When(amount_paid__gte=F('amount_due'), then='amount_paid'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            new_held=Sum(
                Case(
                    When(created_at__date=dt.date.today(), then=F('amount_due') - F('amount_paid')),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            paid_count=Count(
                Case(
                    When(amount_paid__gte=F('amount_due'), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            )
        ).values('total_count', 'total_held', 'new_count', 'new_held', 'paid_sum', 'paid_count')
        print(cols)

        response['repayments'] = self._content
        response['loans_count'] = Collection.objects.filter(user=operator).count()
        response['repayments_count'] = Repayment.objects.filter(admin_user=operator).count()
        response['notes_count'] = Note.objects.filter(user=operator).count()
        response['mini_show'] = f"""
                <ul class="list-group">
                    <ul class="list-group">
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div class="col-6 pe-0">Total</div>
                            <div class="col-6 text-end">
                                <span class="badge bg-primary p-2">{cols[0]['total_count']}</span>
                                <span class="badge bg-secondary p-2">&#x20A6; {cols[0]['total_held']:,}</span>
                            </div>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div class="col-6 pe-0">New</div>
                            <div class="col-6 text-end">
                                <span class="badge bg-primary p-2">{cols[0]['new_count']}</span>
                                <span class="badge bg-secondary p-2">&#x20A6; {cols[0]['new_held']:,}</span>
                            </div>
                        </li>
                        <li class="list-group-item d-flex justify-content-between align-items-center">
                            <div class="col-6 pe-0">Repaid</div>
                            <div class="col-6 text-end">
                                <span class="badge bg-primary p-2">{cols[0]['paid_count']}</span>
                                <span class="badge bg-secondary p-2">&#x20A6; {cols[0]['paid_sum']:,}</span>
                            </div>
                        </li>
                    </ul>
        """
        self._content = response

    def add_admin(self):
        if AdminUser.objects.filter(level=self.kwargs['level'], stage=self.kwargs['stage']).exists():
            last_stage_admin = AdminUser.objects.filter(level=self.kwargs['level'], stage=self.kwargs['stage']).last()
            next_stage_id = last_stage_admin.stage_id + 1
        else:
            next_stage_id = 1
        AdminUser(
            first_name=self.kwargs['first_name'],
            last_name=self.kwargs['last_name'],
            phone=self.kwargs['phone'],
            password=make_password(self.kwargs['password']),
            level=self.kwargs['level'],
            stage=self.kwargs['stage'],
            stage_id=next_stage_id
        ).save()
        self._message = f'{self.kwargs["level"].title()} {self.kwargs["stage"]}-{Func.format_agent_id(next_stage_id)} added successfully'
        self._status = 'success'

    def accepted_users(self):
        main_action = self.kwargs['main_action']
        phone = Func.format_phone(self.kwargs['phone'])
        if main_action == 'add':
            if not AcceptedUser.objects.filter(phone=phone).exists():
                AcceptedUser(phone=phone, admin_user=self.admin_user).save()
                self._status = 'success'
                self._message = 'Added'
            else:
                self._status = 'info'
                self._message = 'Already exists'
        elif main_action == 'remove':
            if AcceptedUser.objects.filter(phone=phone).exists():
                AcceptedUser.objects.get(phone=phone).delete()
                self._status = 'success'
                self._message = 'Deleted'
            else:
                self._status = 'info'
                self._message = 'Does not exists'

    def fetch_accepted_users(self,
                             rows=10,
                             start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                             end=f'{dt.date.today():%Y-%m-%d}',
                             filters=''
                             ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        users = AcceptedUser.objects.filter(
                (
                        Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
                )
                &
                (
                        Q(phone__startswith=filters)
                )
            ).order_by('-created_at').all()

        self._content = ''
        rows = int(rows)
        sn = 0

        for user in users:
            if rows > 0:
                sn += 1
                self.add_table_content(_for='accepted_users', row=user, sn=sn)

    def modify_admin(self):
        admin = AdminUser.objects.get(pk=self.kwargs['user_id'])
        admin.first_name = self.kwargs['first_name']
        admin.last_name = self.kwargs['last_name']
        admin.phone = self.kwargs['phone']
        if self.kwargs['password'] != '':
            admin.password = make_password(self.kwargs['password'])
        admin.save()
        self._message = 'Modified successfully'
        self._status = 'success'

    def can_collect(self):
        admin = AdminUser.objects.get(pk=self.kwargs['user_id'])
        if admin.level != 'staff':
            self._status = 'warning'
            self._message = 'Function is only applicable to Staff'
        else:
            if admin.can_collect:
                admin.can_collect = False
                self._message = 'Staff collection disabled'
                self._status = 'info'
            else:
                admin.can_collect = True
                self._message = 'Staff collection enabled'
                self._status = 'success'
            admin.save()

    def delete_operator(self):
        admin = AdminUser.objects.get(pk=self.kwargs['user_id'])
        if self.admin_user.level in ['super admin', 'admin']:
            admin.delete()
            self._message = 'Operator deleted successfully'
        else:
            self._message = 'No such privilege'

    def add_table_content(self, _for='', **kwargs):
        if _for == 'operators':
            agent = kwargs['agent']
            sn = kwargs['sn']
            if not agent.status:
                status_class = 'danger'
                status_text = 'Suspended'
            elif agent.level == 'staff':
                if agent.status and agent.can_collect:
                    status_class = 'success'
                    status_text = 'Active, C-C'
                else:
                    status_class = 'info'
                    status_text = 'Active, N-C'
            else:
                status_class = 'success'
                status_text = 'Active'

            if agent.level == 'super admin':
                level_class = 'primary'
            elif agent.level == 'admin':
                level_class = 'secondary'
            elif agent.level == 'approval admin':
                level_class = 'warning'
            elif agent.level == 'team leader':
                level_class = 'info'
            else:
                level_class = 'dark'

            stage = f'{agent.stage} - {Func.format_agent_id(agent.stage_id)}'
            if agent.level == 'team leader':
                stage = f'TL - {agent.stage}.{agent.stage_id}'

            rate = kwargs['recovery']
            if rate != '':
                if rate < 10:
                    rate_class = 'danger'
                elif 10 <= rate < 40:
                    rate_class = 'warning'
                elif 40 <= rate < 70:
                    rate_class = 'primary'
                else:
                    rate_class = 'success'
                show_rate = f""" <div class="progress radius-10 mt-4" style="height:9px;">
							<div class="progress-bar bg-{rate_class}" role="progressbar" style="width: {rate}%"></div> <small style="font-size: 9px" class='fw-bold ps-1'>{rate}%</small>
						</div>"""
            else:
                show_rate = '-'

            self._content += f"""
                <tr class='user_trs' 
                data-id='{agent.id}' 
                data-first_name='{agent.first_name}' 
                data-last_name="{agent.last_name}" 
                data-email='{agent.email}' 
                data-phone='{agent.phone}'
                data-level={agent.level}
                data-stage='{agent.stage}'
                data-created_at="{agent.created_at:%a %b %d, %Y}" 
                data-avatar="/static/admin_panel/images/avatars/user.png" 
                data-status_pill='<span class="badge rounded-pill text-bg-{status_class}">{status_text}</span>' 
                data-bs-toggle='modal' data-bs-target='#operatorModal'>
				    <td>
				    {sn}
				    </td>
				    <td>{agent.first_name}</td>
				    <td>
					    <div class='badge rounded-pil w-50 text-bg-{level_class}'>{agent.level.title()}</div>
				    </td>
				    <td>
					    <div class='badge rounded-pill w-50 text-bg-dark'>{stage}</div>
				    </td>
				    <td>
					    <div class='badge rounded-pill w-50 text-bg-{status_class}'>{status_text}</div>
				    </td>
				    <td>
				        {show_rate}
				    </td>
				    <td>{agent.last_login:%d %b, %H:%M}</td>	
			    </tr>
            """

        elif _for == "operator_loans":
            col: Collection = kwargs['col']
            loan = col.loan

            status_text, status_class = Func.get_loan_status(loan)
            avatar = f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{loan.user.avatar.name}" if hasattr(loan.user, "avatar") else "/static/admin_panel/images/avatars/user.png"

            self._content += f"""
                <tr data-user_id='{loan.user.user_id}' 
                                    data-eligible_amount='{loan.user.eligible_amount:,}' 
                                    data-first_name='{loan.user.first_name}' 
                                    data-last_name='{loan.user.last_name}' 
                                    data-phone='{loan.user.phone}' 
                                    data-phone2='{loan.user.phone2}' 
                                    data-middle_name='{loan.user.middle_name}' 
                                    data-email='{loan.user.email}' 
                                    data-gender='{loan.user.gender}' 
                                    data-state='{loan.user.state}' 
                                    data-lga='{loan.user.lga}' 
                                    data-email2='{loan.user.email2}' 
                                    data-address='{loan.user.address}' 
                                    data-dob='{loan.user.dob}' 
                                    data-created_at="{loan.user.created_at:%a %b %d, %Y}" 
                                    data-avatar="{avatar}" 
                                    data-status='{'Active' if not loan.user.is_blacklisted() else 'Blacklisted'}' 
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if not loan.user.is_blacklisted() else 'danger'}">{'Active' if not loan.user.is_blacklisted() else f'Blacklisted: {getattr(loan.user, "blacklist").created_at:%b %d}'}</span>'
                                    data-style='grey' 
                                    data-last_access='{loan.user.last_access}' class='loan_rows'
                                    data-loan_id='{loan.loan_id}'">
                        <td>
								<div class="d-flex align-items-center">
									
									<div class="ms-2">
										<h6 class="mb-0 font-14 fw-bold">{loan.loan_id}
										<span style="font-size: 11px" class="fw-bold text-{'warning' if loan.reloan == 1 else 'info'}">{'1st' if loan.reloan == 1 else f'({loan.reloan})'}</span>
										</h6>
										<p class="mb-0 font-13 text-{'danger' if loan.user.is_blacklisted() else 'secondary'}">{loan.user.last_name} {loan.user.first_name}</p>
									</div>
								</div>
							</td>
                        <td>&#x20A6;{loan.principal_amount:,}</td>
                        <td>&#x20A6;{loan.amount_disbursed:,}</td>
                        <td>&#x20A6;{loan.amount_due:,}</td>
                        <td>&#x20A6;{loan.amount_paid:,.2f} {'<span class="rounded-pill badge text-bg-dark">waive</span>' if loan.waive_set.exists() else ''}</td>
                        <td>{loan.disbursed_at:%b %d, %Y}</td>
                        <td>{AdminUtils.get_due_date(loan)}</td>
                        <td>{AdminUtils.overdue_days(loan)}</td>
                        <td>
                            <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text.title()} {Func.get_stage(loan)}</div>
                        </td>
                    """

            self._content += f"""
                			<td>
                				<div class='dropdown ms-auto'>
                				<div data-bs-toggle='dropdown' class='dropdown-toggle dropdown-toggle-nocaret cursor-pointer' aria-expanded='false'>
                				<i class='bx bx-dots-vertical-rounded font-22'></i>
                			</div>
                			<ul class='dropdown-menu' style='cursor: pointer;'>
                        """
            if self.admin_user.level in ['super admin', 'approval admin', 'staff']:
                if loan.status not in ['repaid', 'declined', 'pending', 'approved']:
                    self._content += f"""
                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-action='repaid' class='loan_actions text-success'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Write Off</a></li>
                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-bs-toggle='modal' data-bs-target='#WaiveModal' class='text-success waive'><a class='dropdown-item'><i class='bx bxs-hand-up font-22 '></i> Waive</a></li>
                    """
                if loan.status == "pending":
                    self._content += f"""
                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-action='approved' class='loan_actions text-success'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Approve</a></li>
                        <li data-id='{loan.id}' data-action='declined' class='loan_actions text-danger'><a class='dropdown-item'><i class='bx bx-x font-22 '></i> Decline</a></li>
                    """
                if loan.status == "approved":
                    self._content += f"""
                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-action='disbursed' class='loan_actions text-primary'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Disburse</a></li>
                    """

                if self.admin_user.level == 'super admin':
                    self._content += f"""
                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-action='trash_loan' class='loan_actions'><a class='dropdown-item'><i class='bx bx-trash font-22 '></i> Trash Loan</a></li>
                        """
            self._content += f"""
                            </ul>
                        </div>
                    </td>
                """
            self._content += "</tr>"

        elif _for == "operator_repayments":
            repay = kwargs['repay']
            loan = repay.loan

            if repay.total_paid < repay.amount_due:
                status_text = 'Partial'
                status_class = 'warning'
            else:
                status_text = 'Repaid'
                status_class = 'success'

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}'">
                            <td>
								<div class="d-flex align-items-center">
									
									<div class="ms-2">
										<h6 class="mb-0 font-14 fw-bold">{loan.loan_id}
										<span style="font-size: 11px" class="fw-bold text-{'warning' if loan.reloan == 1 else 'info'}">{'1st' if loan.reloan == 1 else f'({loan.reloan})'}</span>
										</h6>
										<p class="mb-0 font-13 text-{'danger' if loan.user.is_blacklisted() else 'secondary'}">{loan.user.last_name} {loan.user.first_name}</p>
									</div>
								</div>
							</td>
                			<td>&#x20A6;{loan.principal_amount:,}</td>
                			<td>&#x20A6;{loan.amount_due:,}</td>
                			<td>&#x20A6;{repay.amount_paid_now:,}</td>
                			<td>{Func.get_stage(loan)}</td>
                			<td>&#x20A6;{repay.total_paid:,.2f}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text} </div>
                            </td>
                            <td>{repay.created_at:%b %d, %Y}</td>
                            </tr>
                		"""

        elif _for == 'logs':
            row = kwargs['row']
            self._content += f"""
                <tr>
                    <td>{row.action.title()}</td>
                    <td>&#x20A6;{row.fee:,}</td>
                    <td>{row.body}</td>
                    <td>
					    <div class='badge rounded-pill w-50 text-bg-{row.status}'>{row.status.title()}</div>
				    </td>
                    <td>{row.created_at:%a %b %d, %Y}</td>
                </tr>

            """

        elif _for == 'accepted_users':
            row = kwargs['row']
            sn = kwargs['sn']
            self._content += f"""
                            <tr>
                                <td>{sn}.</td>
                                <td>{row.phone}</td>
                                <td>{row.created_at:%a %b %d, %Y}</td>
                                <td><a href="#0" data-phone="{row.phone}" class="remove">remove</a></td>
                            </tr>

                        """

    def process(self):
        if self.action == "fetch_operators":
            self.fetch_operators()
        elif self.action == "fetch_assigned":
            self.fetch_assigned(Loan.objects.get(loan_id=self.kwargs['loan_id']))
        elif self.action == "assign":
            self.assign(
                loan=Loan.objects.get(loan_id=self.kwargs['loan_id']),
                action=self.kwargs.get('main_action'),
                collector=AdminUser.objects.get(pk=self.kwargs.get('collector_id'))
            )
        elif self.action == "operator_details":
            self.operator_details()
        elif self.action == "add_account":
            self.add_admin()
        elif self.action == "modify_account":
            self.modify_admin()
        elif self.action == "can_collect":
            self.can_collect()
        elif self.action == "delete_operator":
            self.delete_operator()
        elif self.action == 'fetch_logs':
            self.fetch_logs()
        elif self.action == 'accepted_user':
            self.accepted_users()
        elif self.action == 'fetch_accepted_users':
            self.fetch_accepted_users()

    @staticmethod
    def overdue_days(loan):
        if loan.disbursed_at is not None:
            due_date = loan.disbursed_at + dt.timedelta(days=loan.duration)
            diff = timezone.now() - due_date
            if diff.days < -1:
                return '-' if loan.status != 'repaid' else f'repaid: {loan.repaid_at:%b %d}'
            return diff.days if loan.status != 'repaid' else f'repaid: {loan.repaid_at:%b %d}'
        return '-'

    @staticmethod
    def get_due_date(loan):
        if loan.disbursed_at is not None:
            return f'{(loan.disbursed_at + dt.timedelta(days=loan.duration)):%b %d, %Y}'
        return '-'

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        self._content = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value


class LoanUtils:
    def __init__(self, request, **kwargs):
        self.user, self.users, self.user_id, self._content, self._content2, self.loan = None, None, None, None, None, None
        self.kwargs = kwargs
        self.action = self.kwargs['action']
        self.request = request
        self._status, self._message = 'success', 'success'

    def fetch_loans(self, size="single", rows=10, start=f'{dt.date.today()-dt.timedelta(days=60):%Y-%m-%d}', end=f'{dt.date.today():%Y-%m-%d}', status='pending,approved,disbursed,declined,partpayment,repaid,overdue', overdue_start=-LOAN_DURATION, overdue_end=365, filters=''):
        if size != 'single':
            start_date = dt.datetime.strptime(start, '%Y-%m-%d')
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

            end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
            end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

            loans = Loan.objects.filter(
                (
                        Q(created_at__gte=start_date) & Q(created_at__lte=end_date)
                )
                &
                (
                        Q(loan_id__startswith=filters) | Q(user__phone__startswith=filters) |
                        Q(user__bvn__startswith=filters) | Q(user__first_name__startswith=filters) |
                        Q(user__last_name__startswith=filters)
                )
            ).order_by('-created_at').all()

            overdue_from = -LOAN_DURATION if overdue_start == '' else int(overdue_start)
            overdue_to = 365 if overdue_end == '' else int(overdue_end)
            rows = int(rows)

            self._content = ''
            sn = 0
            for loan in loans:
                if self.request.user.level in ('super admin', 'approval admin') or (self.request.user.level == 'team leader' and self.request.user.stage == Func.get_stage(loan)):
                    if rows > 0:
                        if loan.status not in ('disbursed', 'partpayment') and overdue_start == '':
                            overdue_days = overdue_from  # When filter not given, show loan even if not disbursed yet
                        elif loan.status not in ('disbursed', 'partpayment') and overdue_start != '':
                            overdue_days = -10  # Don't show this loan if filter is given
                        else:
                            overdue_days = Func.overdue_days(loan.disbursed_at, loan.duration)

                        if loan.status == 'repaid' and overdue_start != '':
                            overdue_days = -10
                        if overdue_from <= overdue_days <= overdue_to:
                            statuses = status.split(',')
                            sn += 1
                            if len(statuses) == 1 and 'overdue' in statuses:
                                if Func.get_loan_status(loan)[0] == 'overdue' and loan.status != 'repaid':
                                    self.add_table_content(_for='loans', single=False, loan=loan, sn=sn, size=size)
                            elif loan.status == 'disbursed':
                                if 'disbursed' in statuses and overdue_days < 0:
                                    self.add_table_content(_for='loans', single=False, loan=loan, sn=sn, size=size)
                            elif loan.status in statuses:
                                self.add_table_content(_for='loans', single=False, loan=loan, sn=sn, size=size)
                            rows -= 1
        else:
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            # IF SIZE IS SINGLE
            loans = self.user.loan_set.order_by('-created_at').all()
            self._content = ''
            sn = 0
            for loan in loans:
                sn += 1
                self.add_table_content(_for='loans', single=True, loan=loan, sn=sn, size=size)

    def fetch_waives(self, rows=10, start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                    end=f'{dt.date.today():%Y-%m-%d}'):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        waives = Waive.objects.order_by(
            '-created_at').all()

        self._content = ''
        sn = 0
        for waive in waives[:int(rows)]:
            sn += 1
            self.add_table_content(_for='waives', waive=waive, sn=sn)

    def fetch_repayments(self, size="single", rows=10, start=f'{dt.date.today()-dt.timedelta(days=60):%Y-%m-%d}', end=f'{dt.date.today():%Y-%m-%d}'):
        if size != 'single':
            start_date = dt.datetime.strptime(start, '%Y-%m-%d')
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

            end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
            end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

            repayments = Repayment.objects.filter(created_at__gte=start_date, created_at__lte=end_date).order_by('-id').all()

            self._content = ''
            rows = int(rows)

            sn = 0
            for repay in repayments:
                if rows > 0:
                    if self.request.user.level in ('super admin', 'approval admin') or (repay.admin_user == self.request.user and self.request.user.level == 'staff') or (self.request.user.level == 'team leader' and self.request.user.stage == repay.admin_user.stage):
                        sn += 1
                        self.add_table_content(_for='repayments', single=False, repay=repay, sn=sn, size=size)
                        rows -= 1
        else:
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            # IF SIZE IS SINGLE
            repayments = self.user.repayment_set.order_by('-id').all()
            self._content = ''
            sn = 0
            for repay in repayments:
                sn += 1
                self.add_table_content(_for='repayments', single=True, repay=repay, sn=sn, size=size)

    def status_update(self, to):
        qty = self.kwargs.get('qty', 'single')
        if qty == 'single':
            loan = Loan.objects.get(pk=self.kwargs['loan_id'])
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            if to == "repaid":
                if loan.status in ['repaid', 'declined', 'pending']:
                    self._message = 'Action could not be completed, refresh page and try again'
                    self._status = 'error'
                    return
                elif self.request.user.level not in ('super admin', 'approval admin'):
                    self._message = 'Permission error. Please contact an approval admin'
                    self._status = 'error'
                    return
                Func.repayment(loan=loan, amount_paid=loan.amount_due-loan.amount_paid)
            else:
                # IF TO == 'APPROVED' OR 'DECLINED' OR 'DISBURSED'
                if to == "disbursed" and loan.status != "approved":
                    self._message = 'Please approve request before disbursement'
                    self._status = 'error'
                    return
                if to != "disbursed" and loan.status != "pending":
                    self._message = 'Action could not be completed, refresh page and try again'
                    self._status = 'error'
                    return

            if to == "disbursed":
                if not Func.disburse_loan(loans=[loan], admin_user=self.request.user):
                    self._message = 'Disbursement Failed'
                    self._status = 'error'
                    return

            if to != 'disbursed':
                loan_static = LoanStatic(user=self.request.user, loan=loan, status=to)
                loan_static.save()
            loan.status = to
            loan.decline_reason = self.kwargs.get('reason', '')

            if to == 'declined':
                loan.user.notification_set.create(
                    message=f'Your loan request of N{loan.principal_amount:,} was declined',
                    message_type='loan_request'
                )

            AdminUtils.log(
                user=self.request.user,
                app_user=loan.user,
                action_type='loan status',
                action=f'{to.title()} a loan with ID {loan.loan_id}')
            loan.save()
            self._message = f'Loan {to} successfully'
            self._status = 'success'
            self.fetch_loans(size=self.kwargs['size'])
        else:
            # IF IN BULK
            loan_ids = json.loads(self.kwargs.get('loans'))
            loans = [Loan.objects.get(loan_id=lid) for lid in loan_ids]
            if to != 'disburse':
                for loan in loans:
                    if to == "write-off":
                        if loan.status in ['repaid', 'declined', 'pending']:
                            self._message = 'Action could not be completed, refresh page and try again'
                            self._status = 'error'
                            return
                        elif self.request.user.level not in ('super admin', 'approval admin'):
                            self._message = 'Permission error. Please contact an approval admin'
                            self._status = 'error'
                            return
                        Func.repayment(loan=loan, amount_paid=loan.amount_due - loan.amount_paid)
                    else:
                        # IF TO == 'APPROVED' OR 'DECLINED'
                        if to in ['approve', 'decline'] and loan.status != "pending":
                            self._message = 'Action could not be completed, refresh page and try again'
                            self._status = 'error'
                            return

                    if to == 'waive':
                        status = 'repaid'
                    elif to == 'approve':
                        status = 'approved'
                    elif to == 'decline':
                        status = 'declined'
                    else:
                        status = ''
                    loan_static = LoanStatic(user=self.request.user, loan=loan, status=status)
                    loan.status = status
                    loan.decline_reason = self.kwargs.get('reason', '')

                    AdminUtils.log(
                        user=self.request.user,
                        app_user=loan.user,
                        action_type='loan status',
                        action=f'{status.title()} a loan with ID {loan.loan_id}')
                    loan_static.save()
                    loan.save()
            else:
                # IF TO == 'DISBURSED'
                if not Func.disburse_loan(loans=loans, admin_user=self.request.user):
                    self._message = 'Disbursement Failed'
                    self._status = 'error'
                    return

    def trash_loan(self):
        loan = Loan.objects.get(pk=self.kwargs['loan_id'])
        loan.delete()
        AdminUtils.log(user=self.request.user, app_user=loan.user, action_type='loan status', action=f'Deleted a loan with ID {loan.loan_id}')
        self._message = f'Loan request deleted successfully'
        self._status = 'success'
        self.fetch_loans(size=self.kwargs['size'])

    def waive_loan(self):
        loan = Loan.objects.get(pk=self.kwargs.get('loan_id'))
        amount = self.kwargs.get('amount')
        loan_obj = None
        if self.request.user.level in ['super admin', 'approval admin']:
            if amount and loan:
                if float(amount) > loan.amount_due - loan.amount_paid:
                    self._message = f'Amount to waive cannot be greater than amount due'
                    self._status = 'error'
                    return
                loan.amount_due -= float(amount)
                if loan.amount_due == 0:
                    loan.status = 'repaid'
                    loan.repaid_at = timezone.now()
                Waive(admin_user=self.request.user, loan=loan, waive_amount=float(amount), status='approved', modified_at=timezone.now()).save()
                loan.save()
                loan_obj = loan
            else:
                waive = Waive.objects.get(pk=self.kwargs.get('waive_id'))
                amount = waive.waive_amount
                waive.loan.amount_due -= float(amount)
                if waive.loan.amount_due == 0:
                    waive.loan.status = 'repaid'
                    waive.loan.repaid_at = timezone.now()
                waive.status = 'approved'
                waive.modified_at = timezone.now()
                waive.save()
                loan_obj = waive.loan
            self._message = f'Loan waive successful'
            self._status = 'success'
            self.fetch_waives()
        if loan_obj and Collection.objects.filter(loan=loan_obj).exists():
            collection = Collection.objects.get(loan=loan_obj)
            collection.amount_due = loan_obj.amount_due
        else:
            if Waive.objects.filter(loan=loan, status='pending').exists():
                self._message = f'A pending waive for this loan exists'
                self._status = 'error'
                return
            elif float(amount) > loan.amount_due - loan.amount_paid:
                self._message = f'Amount to waive cannot be greater than amount due'
                self._status = 'error'
                return
            else:
                Waive(admin_user=self.request.user, loan=loan, waive_amount=float(amount)).save()
                self._message = f'Waive submitted successfully'
                self._status = 'info'
            self.fetch_loans(size=self.kwargs['size'])

    def add_table_content(self, _for='', **kwargs):
        if _for == "loans":
            loan = kwargs['loan']
            self.loan = loan
            if not kwargs['single']:
                attach_user = f"{loan.user.last_name} {loan.user.first_name}"
            else:
                attach_user = ''

            avatar = f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{loan.user.avatar.name}" if hasattr(loan.user, "avatar") else "/static/admin_panel/images/avatars/user.png"

            status_text, status_class = Func.get_loan_status(loan)
            if status_text == 'disbursed' and loan.disburse_id == '':
                status_text = 'disbursing...'
                status_class = 'info'

            disbursed = '-'
            amt_due = '-'
            amt_paid = '-'
            if loan.disbursed_at is not None:
                disbursed = f'{loan.disbursed_at:%b %d, %Y}'
                amt_due = f'&#x20A6;{loan.amount_due:,}'
                amt_paid = f'&#x20A6;{loan.amount_paid:,.2f}'


            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}' 
                                    data-eligible_amount='{loan.user.eligible_amount:,}' 
                                    data-first_name='{loan.user.first_name}' 
                                    data-last_name='{loan.user.last_name}' 
                                    data-phone='{loan.user.phone}' 
                                    data-phone2='{loan.user.phone2}' 
                                    data-middle_name='{loan.user.middle_name}' 
                                    data-email='{loan.user.email}' 
                                    data-gender='{loan.user.gender}' 
                                    data-state='{loan.user.state}' 
                                    data-lga='{loan.user.lga}' 
                                    data-email2='{loan.user.email2}' 
                                    data-address='{loan.user.address}' 
                                    data-dob='{loan.user.dob}' 
                                    data-created_at="{loan.user.created_at:%a %b %d, %Y}" 
                                    data-avatar="{avatar}" 
                                    data-status='{'Active' if not loan.user.is_blacklisted() else 'Blacklisted'}' 
                                    data-doc_status="{loan.user.status}"
                                    data-doc_reason="{loan.user.status_reason}"
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if not loan.user.is_blacklisted() else 'danger'}">{'Active' if not loan.user.is_blacklisted() else f'Blacklisted: {getattr(loan.user, "blacklist").created_at:%b %d}'}</span>'
                                    data-style='grey' 
                                    data-last_access='{loan.user.last_access}' class='loan_rows'
                                    data-loan_id='{loan.loan_id}'">
                           
                           <td>
								<div class="d-flex align-items-center">
									<div class="loan-checkbox-cont">
										<input class="form-check-input me-3 loan-checkbox border-primary border-2" type="checkbox" value="" aria-label="...">
									</div>
									<div class="ms-2">
										<h6 class="mb-0 font-14 fw-bold">{loan.loan_id}
										<span style="font-size: 11px" class="fw-bold text-{'warning' if loan.reloan == 1 else 'info'}">{'1st' if loan.reloan == 1 else f'({loan.reloan})'}</span>
										</h6>
										<p class="mb-0 font-13 text-{'danger' if loan.user.is_blacklisted() else 'secondary'}">{attach_user}</p>
									</div>
								</div>
							</td>
                          
                			<td>&#x20A6;{loan.principal_amount:,}</td>
                			<td>&#x20A6;{loan.amount_disbursed:,}</td>
                			<td>{amt_due}</td>
                			<td>{amt_paid} {'<span class="rounded-pill badge text-bg-dark">waive</span>' if loan.waive_set.exists() else ''}</td>
                			<td>{loan.created_at:%b %d, %Y}</td>
                			<td>{disbursed}</td>
                			<td>{Func.get_due_date(loan)}</td>
                			<td>{self.overdue_days()}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text.title()} {Func.get_stage(loan)}</div>
                            </td>"""
            if kwargs['size'] == 'single':
                self._content += f"""
                			<td>
                				<div class='dropdown ms-auto'>
                				<div data-bs-toggle='dropdown' class='dropdown-toggle dropdown-toggle-nocaret cursor-pointer' aria-expanded='false'>
                				<i class='bx bx-dots-vertical-rounded font-22'></i>
                			</div>
                			<ul class='dropdown-menu' style='cursor: pointer;'>
                        """
                if self.request.user.level in ['super admin', 'approval admin']:
                    if loan.status not in ['repaid', 'declined', 'pending', 'approved']:
                        self._content += f"""
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='repaid' class='loan_actions text-success'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Write Off</a></li>
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-bs-toggle='modal' data-bs-target='#WaiveModal' class='text-success waive'><a class='dropdown-item'><i class='bx bxs-hand-up font-22 '></i> Waive</a></li>
                                        """
                    if loan.status == "pending":
                        self._content += f"""
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='approved' class='loan_actions text-success'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Approve</a></li>
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='declined' class='loan_actions text-danger'><a class='dropdown-item'><i class='bx bx-x font-22 '></i> Decline</a></li>
                                        """
                    if loan.status == "approved":
                        self._content += f"""
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='disbursed' class='loan_actions text-primary'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Disburse</a></li>
                                        """
                    if loan.status == "declined":
                        self._content += f"""
                                        <li data-reason_head='Reason Loan {loan.loan_id} was declined: ' data-reason_body='{loan.decline_reason}' class='see_reason text-primary'><a class='dropdown-item'><i class='bx bx-question-mark font-22 '></i> See Reason</a></li>
                                        """

                    self._content += f"""
                    <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='trash_loan' class='loan_actions'><a class='dropdown-item'><i class='bx bx-trash font-22 '></i> Trash Loan</a></li>
                    """
                self._content += f"""
                            </ul>
                        </div>
                    </td>
                """
            self._content += "</tr>"

        if _for == "repayments":
            repay = kwargs['repay']
            loan = repay.loan
            self.loan = loan

            avatar = f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{loan.user.avatar.name}" if hasattr(loan.user, "avatar") else "/static/admin_panel/images/avatars/user.png"

            if repay.total_paid < repay.amount_due:
                status_text = 'Partial'
                status_class = 'warning'
            else:
                status_text = 'Repaid'
                status_class = 'success'

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}'
                                    data-eligible_amount='{loan.user.eligible_amount:,}' 
                                    data-first_name='{loan.user.first_name}' 
                                    data-last_name='{loan.user.last_name}' 
                                    data-phone='{loan.user.phone}' 
                                    data-phone2='{loan.user.phone2}' 
                                    data-middle_name='{loan.user.middle_name}' 
                                    data-email='{loan.user.email}' 
                                    data-gender='{loan.user.gender}' 
                                    data-state='{loan.user.state}' 
                                    data-lga='{loan.user.lga}' 
                                    data-email2='{loan.user.email2}' 
                                    data-address='{loan.user.address}' 
                                    data-dob='{loan.user.dob}' 
                                    data-created_at="{loan.user.created_at:%a %b %d, %Y}" 
                                    data-avatar="{avatar}" 
                                    data-status='{loan.user.status}' 
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if loan.user.status else 'danger'}">{'Active' if loan.user.status else 'Suspended'}</span>' 
                                    data-style='grey' 
                                    data-last_access='{loan.user.last_access}' class='repay_rows' data-bs-toggle='modal' data-bs-target='#exampleLargeModal1'
                                    data-user_id='{loan.user.user_id}'">
                            <td>
								<div class="d-flex align-items-center">
									
									<div class="ms-2">
										<h6 class="mb-0 font-14 fw-bold">{loan.loan_id}
										<span style="font-size: 11px" class="fw-bold text-{'warning' if loan.reloan == 1 else 'info'}">{'1st' if loan.reloan == 1 else f'({loan.reloan})'}</span>
										</h6>
										<p class="mb-0 font-13 text-{'danger' if loan.user.is_blacklisted() else 'secondary'}">{loan.user.last_name} {loan.user.first_name}</p>
									</div>
								</div>
							</td>
                           
                			<td>&#x20A6;{loan.principal_amount:,}</td>
                			<td>&#x20A6;{loan.amount_due:,}</td>
                			<td>&#x20A6;{repay.amount_paid_now:,.2f}</td>
                			<td>{repay.overdue_days}</td>
                			<td>&#x20A6;{repay.total_paid:,.2f}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text.title()} </div>
                            </td>
                            <td>{repay.created_at:%b %d, %Y}</td>
                            </tr>
                		"""

        if _for == "waives":
            waive = kwargs['waive']
            self.loan, loan = waive.loan, waive.loan

            avatar = f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{loan.user.avatar.name}" if hasattr(loan.user, "avatar") else "/static/admin_panel/images/avatars/user.png"

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}' 
                                    data-eligible_amount='{loan.user.eligible_amount:,}' 
                                    data-first_name='{loan.user.first_name}' 
                                    data-last_name='{loan.user.last_name}' 
                                    data-phone='{loan.user.phone}' 
                                    data-phone2='{loan.user.phone2}' 
                                    data-middle_name='{loan.user.middle_name}' 
                                    data-email='{loan.user.email}' 
                                    data-gender='{loan.user.gender}' 
                                    data-state='{loan.user.state}' 
                                    data-lga='{loan.user.lga}' 
                                    data-email2='{loan.user.email2}' 
                                    data-address='{loan.user.address}' 
                                    data-dob='{loan.user.dob}' 
                                    data-created_at="{loan.user.created_at:%a %b %d, %Y}" 
                                    data-avatar="{avatar}" 
                                    data-status='{loan.user.status}' 
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if loan.user.status else 'danger'}">{'Active' if loan.user.status else 'Suspended'}</span>' 
                                    data-style='grey' 
                                    data-last_access='{loan.user.last_access}' 
                                    data-waive_status='{waive.status}'
                                    class='waive_rows' data-bs-toggle='modal' data-bs-target='#exampleLargeModal1'
                                    data-user_id='{loan.user.user_id}'" data-waive_id="{waive.id}"
                                    data-loan_id='{loan.id}'
                                    > 
                            <td>{kwargs['sn']}.</td>
                            <td>{waive.loan.loan_id}
                            <span class="badge bg-{'warning' if waive.loan.reloan == 1 else 'info'}">{'1st loan' if waive.loan.reloan == 1 else f'reloan ({waive.loan.reloan})'}</span>
                            </td>
                            <td>&#x20A6;{waive.loan.principal_amount:,}</td>
                			<td>&#x20A6;{waive.loan.amount_disbursed:,}</td>
                			<td>&#x20A6;{waive.loan.amount_due:,}</td>
                			<td>&#x20A6;{waive.loan.amount_paid:,}</td>
                			<td>&#x20A6;{waive.waive_amount:,}</td>
                			<td>{Func.get_due_date(waive.loan)}</td>
                			<td>{self.overdue_days()}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{"warning" if waive.status == "pending" else "success"}'>{waive.status.title()} </div>
                            </td>
                			</tr>"""

    def process(self):
        if self.action == "fetch_all_loans":
            self.fetch_loans(size='multiple',
                             rows=self.kwargs.get('rows', 10),
                             start=self.kwargs.get('start'),
                             end=self.kwargs.get('end'),
                             status=self.kwargs.get('status'),
                             filters=self.kwargs.get('filters'),
                             overdue_start=self.kwargs.get('overdue_start'),
                             overdue_end=self.kwargs.get('overdue_end')
                             )
        else:
            if self.action == "fetch_loans":
                self.fetch_loans(size='single')
            elif self.action == "status_update":
                if self.kwargs['main_action'] == "trash_loan":
                    self.trash_loan()
                else:
                    self.status_update(self.kwargs['main_action'])
            elif self.action == "fetch_all_repayments":
                self.fetch_repayments(size='multiple', rows=self.kwargs.get('rows', 10))
            elif self.action == "fetch_repayments":
                self.fetch_repayments(size='single', rows=self.kwargs.get('rows', 10))
            elif self.action == "fetch_waives":
                self.fetch_waives(
                    rows=self.kwargs.get('rows', 10),
                    start=self.kwargs.get('start'),
                    end=self.kwargs.get('end')
                )
            elif self.action == "waive_loan":
                self.waive_loan()

    def overdue_days(self):
        if self.loan.disbursed_at is not None:
            due_date = self.loan.disbursed_at + dt.timedelta(days=self.loan.duration)
            diff = timezone.now() - due_date
            if diff.days < -1:
                return '-' if self.loan.status != 'repaid' else f'<span class="fw-bold text-success">repaid:</span> {self.loan.repaid_at:%b %d}'
            return diff.days if self.loan.status != 'repaid' else f'<span class="fw-bold text-success">repaid:</span> {self.loan.repaid_at:%b %d}'
        return '-'

    @property
    def content(self):
        return self._content

    @content.setter
    def content(self, value):
        self._content = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value

    @property
    def message(self):
        return self._message

    @message.setter
    def message(self, value):
        self._message = value

    @property
    def content2(self):
        return self._content2

    @content2.setter
    def content2(self, value):
        self._content2 = value


class Analysis:
    def __init__(self, request, **kwargs):
        self.kwargs = kwargs
        self.request = request
        self._result, self._content = None, ''

        # if self.request.user.level not in ['super admin', 'admin', 'team leader']:
        #     raise 'You do not have permission to perform this action'

    def real_day(self, date):
        year, month = int(date.split('-')[0]), int(date.split('-')[1])
        loans = Loan.objects.filter(disbursed_at__year=year, disbursed_at__month=month)
        daily_loans = loans.annotate(day=TruncDay('disbursed_at')).values('day').annotate(
            total_count=Count('id'),
            total_sum=Sum('principal_amount'),
            repaid_count=Count(
                Case(
                    When(Q(status='repaid') | Q(amount_paid=F('amount_due')), then='id'),
                    default=Value(None)
                )
            ),
            repaid_sum=Sum(
                Case(
                    When(Q(status='repaid') | Q(amount_paid=F('amount_due')), then='amount_paid'),
                    default=0,
                    output_field=DecimalField()
                )
            )
        ).values('day', 'total_count', 'total_sum', 'repaid_sum', 'repaid_count')

        # convert result to dicts
        daily_loan_dict = {
            loan['day'].day:
                {
                    'total_count': loan['total_count'],
                    'total_sum': loan['total_sum'],
                    'repaid_sum': loan['repaid_sum'],
                    'repaid_count': loan['repaid_count']
                }
            for loan in daily_loans
        }

        num_days = int(monthrange(year, month)[1])
        # Get final daily loan list
        final_list = [{
            'day': f'{self.add_zero(day)}/{self.add_zero(month)}',
            'total_count': int(daily_loan_dict.get(day, {'total_count': 0})['total_count']),
            'total_sum': float(daily_loan_dict.get(day, {'total_sum': 0})['total_sum']),
            'repaid_sum': float(daily_loan_dict.get(day, {'repaid_sum': 0})['repaid_sum']),
            'repaid_count': int(daily_loan_dict.get(day, {'repaid_count': 0})['repaid_count'])
        } for day in range(1, num_days+1)]

        self._result = final_list

    def get_collections(self,
                        stage='S-1,S0',
                        start=f'{dt.date.today() - dt.timedelta(days=500):%Y-%m-%d}',
                        end=f'{dt.date.today():%Y-%m-%d}',
                        ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        stage = stage.split(',')
        collections = Collection.objects.filter(stage__in=stage, loan__disbursed_at__gte=start_date, loan__disbursed_at__lte=end_date).values('user').annotate(
            ciq=Count('id'),
            amount_held=Sum(
                Case(
                    When(amount_paid__lt=F('amount_due'), then=F('amount_due')-F('amount_paid')),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            paid_count=Count(
                Case(
                    When(amount_paid__gte=F('amount_due'), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            partpayment_count=Count(
                Case(
                    When(Q(amount_paid__lt=F('amount_due')) & ~Q(amount_paid=Value(0)), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            amount_paid=Sum('amount_paid'),
            total_amount=Sum('amount_due'),
            notes_count=Count('user__note'),
            new_count=Count(
                Case(
                    When(created_at__date=timezone.now().date(), then='id'),
                    default=Value(None)
                )
            )
        ).values('user', 'ciq', 'amount_held', 'paid_count', 'partpayment_count', 'amount_paid', 'total_amount', 'notes_count', 'new_count')
        result = {
            AdminUser.objects.get(pk=col['user']): {
                'ciq': col['ciq'],
                'amount_held': col['amount_held'],
                'paid_count': col['paid_count'],
                'partpayment_count': col['partpayment_count'],
                'amount_paid': col['amount_paid'],
                'total_amount': col['total_amount'],
                'notes': col['notes_count'],
                'new': col['new_count']
            }
            for col in collections
        }

        self._content = ''
        for user, fields in result.items():
            self.add_table_content(_for='collectors', user=user, fields=fields)
        return self._content

    @staticmethod
    def progressive(start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                    end=f'{dt.date.today():%Y-%m-%d}',
                    dimension='count',
                    loan_type='all'):
        """
        :param start: Start date
        :param end: End date
        :param dimension: could be either 'count' or 'sum'
        :param loan_type: could be either 'all', 'first_loan' or 'reloan'
        :return: 'str' progressive result table
        """
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        progressive = Progressive.objects.filter(disbursed_at__gte=start_date, disbursed_at__lte=end_date).order_by(
            '-disbursed_at').all()
        content = ''
        for pr in progressive:
            content += '<tr>'
            date = f'{pr.disbursed_at:%d-%m-%Y}'
            content += f'<th class="rdp-th" scope="row">{date}</th>'
            fill = ['no data available']
            if loan_type == 'all':
                a_fill, b_fill, total_fill = [], [], []
                if dimension == 'count' or dimension == 'sum':
                    dim = dimension
                    total_fill = [getattr(pr, f'total_{dim}') + getattr(pr, f'total_{dim}_reloan')]
                    a_fill = [getattr(pr, f'a_{dim}') + getattr(pr, f'a_{dim}_reloan')]
                    b_fill = [
                        getattr(pr, f'day{num}_{dim}') + getattr(pr, f'day{num}_{dim}_reloan')
                        for num in range(32)
                    ]
                    if dim == 'sum':
                        total_fill = [f'&#x20A6;{ff:,}' for ff in total_fill]
                        a_fill = [f'&#x20A6;{ff:,}' for ff in a_fill]
                        b_fill = [f'&#x20A6;{ff:,}' for ff in b_fill]
                elif dimension == 'count_rate' or dimension == 'sum_rate':
                    dim = dimension.split('_')[0]
                    total_fill = [getattr(pr, f'total_{dim}') + getattr(pr, f'total_{dim}_reloan')]
                    a_fill = [
                        f"{(((getattr(pr, f'a_{dim}') + getattr(pr, f'a_{dim}_reloan')) / (getattr(pr, f'total_{dim}') + getattr(pr, f'total_{dim}_reloan'))) * 100):.1f}%"
                    ]
                    b_fill = [
                        f"{(((getattr(pr, f'day{num}_{dim}') + getattr(pr, f'day{num}_{dim}_reloan')) / (getattr(pr, f'total_{dim}') + getattr(pr, f'total_{dim}_reloan'))) * 100):.1f}%"
                        for num in range(32)
                    ]

                    if dim == 'sum':
                        total_fill = [f'&#x20A6;{ff:,}' for ff in total_fill]

                fill = total_fill + a_fill + b_fill
            elif loan_type == 'first_loan' or loan_type == 'reloan':
                loantype = '_reloan' if loan_type == 'reloan' else ''
                a_fill, b_fill, total_fill = [], [], []
                if dimension == 'count' or dimension == 'sum':
                    dim = dimension
                    total_fill = [getattr(pr, f'total_{dim}{loantype}')]
                    a_fill = [getattr(pr, f'a_{dim}{loantype}')]
                    b_fill = [
                        getattr(pr, f'day{num}_{dim}{loantype}')
                        for num in range(32)
                    ]

                    if dim == 'sum':
                        total_fill = [f'&#x20A6;{ff:,}' for ff in total_fill]
                        a_fill = [f'&#x20A6;{ff:,}' for ff in a_fill]
                        b_fill = [f'&#x20A6;{ff:,}' for ff in b_fill]
                elif dimension == 'count_rate' or dimension == 'sum_rate':
                    dim = dimension.split('_')[0]
                    total_fill = [getattr(pr, f'total_{dim}{loantype}')]
                    a_fill = [
                        f"{((getattr(pr, f'a_{dim}{loantype}') / getattr(pr, f'total_{dim}{loantype}')) * 100):.1f}%"
                    ]
                    b_fill = [
                        f"{((getattr(pr, f'day{num}_{dim}{loantype}') / getattr(pr, f'total_{dim}{loantype}')) * 100):.1f}%"
                        for num in range(32)
                    ]

                    if dim == 'sum':
                        total_fill = [f'&#x20A6;{ff:,}' for ff in total_fill]

                fill = total_fill + a_fill + b_fill

            for index, item in enumerate(fill):
                if item not in ['0.0%', 0, '&#x20A6;0.0']:
                    show = item
                else:
                    show = ''
                content += f"""
                            <td class="rdp-td">{show}</td>
                        """
        return content

    @staticmethod
    def collection_rates_chart():
        recs = Recovery.objects.values('user__stage').annotate(
            total_rate=Sum('rate'),
            total_count=Count('id')
        ).values('user__stage', 'total_rate', 'total_count')

        recoverys = {
            rec['user__stage']: (rec['total_rate'] / (100 * rec['total_count'])) * 100
            for rec in recs
        }
        data_x = []
        data_y = []
        for stage, perc in recoverys.items():
            # overlook M1 for now cos it's the first item
            if stage != 'M1':
                data_x.append(stage)
                data_y.append(f'{perc:.1f}')
        if recoverys:
            # now add M1 as the last item
            data_x.append('M1')
            data_y.append(f"{recoverys['M1']:.1f}")
        return {
            'x': data_x,
            'y': data_y
        }

    def generate_chart(self, _for=''):
        if _for == 'real_day':
            self._content = ''
            for result in self._result:
                self.add_table_content(_for='real_day', result=result)

    @staticmethod
    def generate_data(_for='', fetch='amount'):
        result = LoanStatic.objects.filter(
            status=f'{_for}'
        ).annotate(
            month=TruncMonth('created_at')
        ).values('month').annotate(
            total_count=Count(
                Case(
                    When(status=f'{_for}', then='id')
                )
            )
        )

        if _for == 'disbursed':
            result = result.annotate(
                total_amount=Sum('loan__amount_disbursed', default=Value(0)),
            )
        elif _for == 'repaid':
            result = result.annotate(
                total_amount=Sum('loan__amount_paid', default=Value(0)),
            )
        elif _for == 'pending' or _for == 'declined':
            result = result.annotate(
                total_amount=Sum('loan__principal_amount', default=Value(0)),
            )

        result.values('month', 'total_amount', 'total_count').order_by('month')
        result = {
            res['month'].month: {
                'amount': res['total_amount'],
                'count': res['total_count']
            }
            for res in result
        }
        # Fill in months that are not available
        for i in range(1, 13):
            if i not in result.keys():
                result[i] = {
                    'amount': 0,
                    'count': 0
                }
        result = dict(sorted(result.items()))
        if fetch == 'amount':
            res_list = [detail['amount'] for res, detail in result.items()]
        else:
            res_list = [detail['count'] for res, detail in result.items()]
        return res_list

    @staticmethod
    def get_dashboard(start, end):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d') + dt.timedelta(days=1)
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        disbursed_count, repaid_count, declined_count, approved_count, overdue_count, pending_count, due_count, partpayment_count = 0, 0, 0, 0, 0, 0, 0, 0
        disbursed_amount, repaid_amount, declined_amount, pending_amount = 0, 0, 0, 0

        static_record = LoanStatic.objects.filter(created_at__gte=start_date, created_at__lte=end_date)
        for rec in static_record:
            if rec.status == 'disbursed':
                disbursed_count += 1
                disbursed_amount += rec.loan.amount_disbursed
            elif rec.status == 'repaid':
                repaid_count += 1
                repaid_amount += rec.loan.amount_paid
            elif rec.status == 'declined':
                declined_count += 1
                declined_amount += rec.loan.principal_amount
            elif rec.status == 'approved':
                approved_count += 1

        loans = Loan.objects.filter(created_at__gte=start_date, created_at__lte=end_date, status__in=['disbursed', 'pending'])
        for loan in loans:
            if loan.status == 'pending':
                pending_count += 1
                pending_amount += (loan.principal_amount - ((loan.interest_perc/100)*loan.principal_amount))
            elif loan.amount_due > loan.amount_paid > 0:
                # loan is partpayment
                partpayment_count += 1
            else:
                status, _ = Func.get_loan_status(loan)
                if status == 'overdue':
                    overdue_count += 1
                elif status == 'due':
                    due_count += 1

        result = {
            'pending_count': f'{pending_count:,}',
            'approved_count': f'{approved_count:,}',
            'disbursed_count': f'{disbursed_count:,}',
            'due_count': f'{due_count:,}',
            'overdue_count': f'{overdue_count:,}',
            'partpayment_count': f'{partpayment_count:,}',
            'repaid_count': f'{repaid_count:,}',
            'declined_count': f'{declined_count:,}',

            'pending_amount': f'{pending_amount:,}',
            'disbursed_amount': f'{disbursed_amount:,}',
            'declined_amount': f'{declined_amount:,}',
            'repaid_amount': f'{repaid_amount:,}'

        }
        return result

    @staticmethod
    def fetch_main_balance():
        return apis.fetch_main_bal()

    def add_table_content(self, _for='', **kwargs):
        if _for == 'real_day':
            result = kwargs['result']
            perc = int((result['repaid_count']/(result['total_count'])) * 100) if result['total_count'] > 0 else 0
            animated = 'progress-bar-animated progress-bar-striped'
            if perc == 100:
                animated = ''
            self._content += f"""
                <div class="progress-container mb-3">
                    <div class="progress-start fw-medium">{result['day']}</div>
                    <div class="progress">
                        <div class="progress-bar progress-bar-bg {animated}" role="progressbar" aria-valuenow="{perc}" aria-valuemin="0" aria-valuemax="100" style="width: {perc}%;"></div>
                        <div class="progress-bar-text">{result['repaid_count']} Loans (&#x20A6;{result['repaid_sum']:,})</div>
                    </div>
                    <div class="progress-end fw-medium">{result['total_count']} (&#x20A6;{result['total_sum']:,})</div>
                </div>
            """
        elif _for == 'collectors':
            user = kwargs['user']
            fields = kwargs['fields']
            self._content += f"""
                <tr>
                    <th scope="row">{user.stage}-{Func.format_agent_id(user.stage_id)}</th>
                    <td>{fields['ciq']:,}</td>
                    <td>{fields['new']:,}</td>
                    <td>&#x20A6; {fields['amount_held']:,}</td>
                    <td>{fields['paid_count']:,}</td>
                    <td>{fields['partpayment_count']:,}</td>
                    <td>{(fields['paid_count']/fields['ciq'])*100:.1f}%</td>
                    <td>&#x20A6;{fields['amount_paid']:,}</td>
                    <td>{(fields['amount_paid']/fields['total_amount'])*100:.1f}%</td>
                    <td>{fields['notes']:,}
                </tr>
            """

    @staticmethod
    def add_zero(num: int):
        if num < 10:
            return f'0{num}'
        return num

    @staticmethod
    def is_in_progressive_category(disbursed_at, day):
        due_date = disbursed_at + dt.timedelta(days=LOAN_DURATION)
        diff = timezone.now() - due_date
        if diff.days == day:
            return True
        return False

    @staticmethod
    def is_in_category(disbursed_at, cat, duration):
        due_date = disbursed_at + dt.timedelta(days=duration)
        diff = timezone.now() - due_date
        stage = 'S0'
        if diff.days == -1:
            stage = 'S-1'
        elif diff.days == 0:
            stage = 'S0'
        elif 1 <= diff.days <= 3:
            stage = 'S1'
        elif 4 <= diff.days <= 7:
            stage = 'S2'
        elif 8 <= diff.days <= 15:
            stage = 'S3'
        elif 16 <= diff.days <= 30:
            stage = 'S4'
        elif diff.days > 30:
            stage = 'M1'
        if cat == stage:
            return True
        return False

    @property
    def result(self):
        return self._result

    @property
    def content(self):
        return self._content




