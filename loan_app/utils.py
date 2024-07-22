from django.http import JsonResponse

from loan_app.models import Loan, DisbursementAccount, VirtualAccount, AppUser, Blacklist, Notification, Otp
from admin_panel.models import LoanStatic, AcceptedUser
from django.contrib.auth.hashers import make_password, check_password
import random
from django.utils import timezone
import datetime as dt
from faker import Faker
from django.db.models import Q, Count
from project_pack.models import Project
import loan_app.api as apis
from admin_panel.utils import Func
import phonenumbers

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import AccessToken


def get_user_from_jwt(request):
    token = request.headers.get('Authorization').split(' ')[1]
    try:
        access_token = AccessToken(token)
        payload = access_token.payload
        return AppUser.objects.get(pk=payload['user_id'])
    except:
        return None


class Auth:
    @staticmethod
    def create_account(**kwargs):
        phone = Misc.format_phone(kwargs['phone'])
        if not AppUser.objects.filter(phone=phone).exists():
            if not AppUser.objects.filter(bvn=kwargs['bvn']).exists():
                if not DisbursementAccount.objects.filter(bank_name=kwargs['bank_details']['bank_name'], number=kwargs['bank_details']['account_number']).exists():
                    user = AppUser(
                        first_name=kwargs['first_name'],
                        last_name=kwargs['last_name'],
                        middle_name=kwargs.get('middle_name'),
                        email=kwargs['email'],
                        email2=kwargs['alternative_email'],
                        marital_status=kwargs['marital_status'],
                        nationality=kwargs['nationality'],
                        password=make_password(kwargs['password']),
                        phone=phone,
                        username=phone,
                        phone2=kwargs['alternative_phone'],
                        bvn=kwargs['bvn'],
                        address=kwargs['address'],
                        dob=dt.datetime.strptime(kwargs['dob'], '%Y-%m-%d'),
                        gender=kwargs['gender'],
                        education=kwargs['education'],
                        children=kwargs['children'],
                        employment=kwargs['employment'],
                        state=kwargs['state'],
                        lga=kwargs['lga'],
                    )
                    user.save()
                    user.user_id = f'SU{user.id}{random.randint(100, 1000)}'
                    user.save()

                    # if kwargs.get('file'):
                    #     Document(
                    #         user=user,
                    #         file=kwargs.get('file'),
                    #         description='User ID',
                    #     ).save()
                    #
                    # if kwargs.get('avatar'):
                    #     Avatar(
                    #         user=user,
                    #         file=kwargs.get('avatar'),
                    #     ).save()

                    # Employment(
                    #     user=user,
                    #     name=kwargs['employment_name'],
                    #     address=kwargs['employment_address'],
                    #     role=kwargs['employment_role'],
                    #     duration=kwargs['employment_duration'],
                    #     salary=kwargs['employment_salary'],
                    #     hr_name=kwargs['employment_hr_name'],
                    #     hr_phone=kwargs['employment_hr_phone'],
                    #     hr_email=kwargs['employment_hr_email']
                    # ).save()
                    #
                    # Emergency(
                    #     user=user,
                    #     family_name=kwargs['emergency_family_name'],
                    #     family_phone=kwargs['emergency_family_phone'],
                    #     family_relationship=kwargs['emergency_family_relationship'],
                    #     family_email=kwargs['emergency_family_email'],
                    #     family_occupation=kwargs['emergency_family_occupation'],
                    #     colleague_name=kwargs['emergency_colleague_name'],
                    #     colleague_email=kwargs['emergency_colleague_email'],
                    #     colleague_phone=kwargs['emergency_colleague_phone'],
                    #     colleague_occupation=kwargs['emergency_colleague_occupation']
                    # )

                    DisbursementAccount(
                        user=user,
                        bank_name=kwargs['bank_details']['bank_name'],
                        number=kwargs['bank_details']['account_number']
                    ).save()
                    Account.update_contacts(user, kwargs['user_contacts'])
                    Account.create_virtual_account(user)
                    return {'status': 'success', 'message': 'Account created'}
                return {'status': 'error', 'message': 'User already exists -ERR101BA'}
            return {'status': 'error', 'message': 'User already exists -ERR102BV'}
        return {'status': 'error', 'message': 'User already exists -ERR102PH'}

    @staticmethod
    def is_phone_exist(phone):
        return AppUser.objects.filter(phone=phone).exists()

    @staticmethod
    def authenticate_user(username, password):
        if AppUser.objects.filter(username=username).exists():
            user = AppUser.objects.get(username=username)
            if check_password(password, user.password):
                user.last_access = timezone.now()
                user.save()
                refresh = RefreshToken.for_user(user)
                access_token = str(refresh.access_token)

                response = JsonResponse({
                    'password_expire': user.last_access + dt.timedelta(days=1),
                    'user_firstName': user.first_name,
                    'user_lastName': user.last_name,
                    'user_middleName': user.middle_name,
                    'user_id': user.user_id,
                    'email': user.email,
                    'service_charge': 0,
                    'user_role': 'user',
                    'is_verified': user.status,
                    'username': user.username
                })
                response['Authorization'] = f'Bearer {access_token}'
                return response

            return JsonResponse({'error': {'status': 401, 'error': 'Invalid credentials -ERRP'}, 'message': 'Http Exception'}, status=401)
        return JsonResponse({'error': {'status': 401, 'error': 'Invalid credentials -ERRNE'}, 'message': 'Http Exception'}, status=401)

    @staticmethod
    def change_password(user, old_password='', new_password=''):
        if check_password(old_password, user.password):
            user.password = make_password(new_password)
            user.save()
            user.notification_set.create(
                message=f'Your password has been updated successfully',
                message_type='password_update'
            )
            return {'status': 'success', 'message': 'Password changed successfully'}
        return {'error': {'status': 401, 'error': 'Current password is incorrect'}, 'message': 'Http Exception'}

    @staticmethod
    def update_password(data):
        # requires: phone, action
        phone = Misc.format_phone(data['phone'])
        user = AppUser.objects.filter(phone=phone).first()
        if user:
            if data['action'] == 'forgot':
                # requires: medium
                # res = apis.send_otp(user=user, length=6, medium=data.get('medium', ['sms']))
                res = {'status': 'success', 'data': {'otp': '1234'}}
                if res['status'] == 'success':
                    Otp.objects.update_or_create(user=user, defaults={'code': res["data"]["otp"], 'expires_at': timezone.now() + dt.timedelta(minutes=10)})
                    return {'status': 'success', 'message': 'A token has been sent to your phone'}
                return {'error': {'status': 500, 'error': 'Token sending failed. Please try again'}, 'message': 'Http Exception'}
            elif data['action'] == 'update':
                # requires: otp, password
                if hasattr(user, 'otp') and user.otp.expires_at > timezone.now():
                    if data['otp'] == user.otp.code:
                        user.password = make_password('2222')
                        user.save()
                        return {'status': 'success', 'message': 'Password updated successfully'}
                    return {'error': {'status': 401, 'error': 'Token is incorrect'}, 'message': 'Http Exception'}
                return {'error': {'status': 401, 'error': 'An error occurred. Please request fresh otp'}, 'message': 'Http Exception'}
        return {'error': {'status': 401, 'error': 'Phone not found'}, 'message': 'Http Exception'}


class Account:
    @staticmethod
    def create_virtual_account(user: AppUser):
        # After creating virtual account, store to db
        res = apis.generate_flw_virtual_account(user)
        if res['status'] == 'success':
            bank_number = res['data']['account_number']
            bank_name = res['data']['bank_name']
            bank_code = 0
        else:
            bank_number = '1234567890'
            bank_name = 'Dummy Bank'
            bank_code = 0
        VirtualAccount(user=user, number=bank_number, bank_name=bank_name, bank_code=bank_code).save()

    @staticmethod
    def generate_dummy_users(count):
        for _ in range(count):
            fake = Faker()
            Auth.create_account(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                email=fake.email(),
                password='0000',
                phone=fake.phone_number(),
                bvn=fake.passport_number(),
                address=fake.address(),
                dob=f'{fake.date_of_birth():%Y-%m-%d}',
                gender=random.choice(['male', 'female']),
                bank_name=random.choice(['Wema Bank', 'GTB', 'Kuda Bank', 'Zenith Bank', 'Union Bank', 'FCMB', 'Access Bank', 'Eco Bank', 'Fidelity Bank', 'OPay', 'Polaris Bank', 'Jaiz Bank']),
                bank_number=fake.iban()
            )

    @staticmethod
    def update_contacts(user: AppUser, data: list):
        existing_phones = [
            user_contact.phone
            for user_contact in user.contact_set.all()
        ]
        for new_contact in data:
            if new_contact['phone'] not in existing_phones:
                user.contact_set.create(phone=new_contact['phone'], name=new_contact['name'])

    @staticmethod
    def update_sms(user, data):
        for content in data:
            for phone, sms_list in content.items():
                for sms in sms_list:
                    category = 'incoming'
                    if sms['dateSent'] == 0:
                        category = 'outgoing'
                    date = int(sms['date'])/1000
                    date_tz = timezone.make_aware(dt.datetime.fromtimestamp(date), timezone.get_current_timezone())
                    user.smslog_set.create(name=phone, phone=phone, message=sms['body'], category=category, date=date_tz)

    @staticmethod
    def fetch_loans(user):
        res = [
            {
                "id": loan.loan_id,
                "requested_amount": loan.principal_amount,
                "amount": loan.principal_amount - ((loan.interest_perc / 100) * loan.principal_amount),
                "amount_disbursed": loan.amount_disbursed,
                "service_charge": loan.interest_perc,
                "repayment_amount": loan.amount_due,
                "interest": (loan.interest_perc / 100) * loan.principal_amount,
                "term": loan.duration,
                "number_of_overdue_days": Func.overdue_days(loan.disbursed_at, loan.duration) if loan.disbursed_at else 'null',
                "status": loan.status.title(),
                "createdAt": f"{loan.created_at:%Y-%m-%dT%H:%M:%S}",
                "updatedAt": f"{loan.updated_at:%Y-%m-%dT%H:%M:%S}",
                "disbursement_date": f'{Misc.format_date(loan.disbursed_at) if loan.disbursed_at else "null"}',
                "due_date": f'{Func.get_due_date(loan, fmt="%Y-%m-%dT%H:%M:%S") if loan.disbursed_at else "null"}',
                "repayment_date": f'{Func.get_due_date(loan, fmt="%Y-%m-%dT%H:%M:%S") if loan.disbursed_at else "null"}',
                "days_till_repayment": -(Func.overdue_days(loan.disbursed_at, loan.duration)) if loan.disbursed_at else 'null',
                "purpose": loan.purpose,
                "repaid": loan.status == 'repaid',
                "overdue": Func.overdue_days(loan.disbursed_at, loan.duration) > 0 if loan.disbursed_at else False,
                "coupon": 0,
                "admin": "",
                "comment": "",
                "user_agreement": "",
                "isActive": loan.status not in ('repaid', 'declined'),
            }
            for loan in user.loan_set.all()
        ]
        return res

    @staticmethod
    def request_loan(user: AppUser, amount, purpose):
        amount = float(amount)
        is_eligible, eligibility_message = Misc.is_eligible(user, amount)
        if is_eligible:
            principal_amount = amount
            amount_due = principal_amount
            reloan = Loan.objects.filter(user=user, status='repaid').count() + 1
            duration = 5 if user.borrow_level == 1 else 10
            new_loan = Loan(user=user, principal_amount=principal_amount,
                            amount_due=amount_due, reloan=reloan, duration=duration, purpose=purpose)
            new_loan.save()
            new_loan.loan_id = f'SL{new_loan.id}{random.randint(100, 1000)}'
            new_loan.save()
            LoanStatic(loan=new_loan, status='pending').save()
            loans = Account.fetch_loans(user)
            user.notification_set.create(
                message=f'Your loan request of N{amount:,} has been received and is being processed',
                message_type='loan_request'
            )
            return {'status': 'success', 'message': 'Loan submitted successfully', 'loan_id': new_loan.loan_id, 'loans': loans}
        return {'error': {'status': 403, 'error': eligibility_message}, 'message': 'Http Exception'}

    @staticmethod
    def fetch_user(user):
        res = {
            "user_id": user.user_id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "middle_name": user.middle_name,
            "phone": user.phone,
            "dob": f'{user.dob:%d-%m-%Y}',
            "gender": user.gender,
            "alternate_phone": user.phone2,
            "email": user.email,
            "alternate_email": user.email2,
            "joining_Date": f"{user.created_at:%Y-%m-%dT%H:%M:%S}",
            "contact_address": user.address,
            "state": user.state,
            "lga": user.lga
        }

    @staticmethod
    def fetch_notifications(user: AppUser):
        res = [
            {
                'id': notif.id,
                'message': notif.message,
                'type': notif.message_type,
                'viewed': notif.viewed,
                'createdAt': Misc.format_date(notif.created_at)
            }
            for notif in user.notification_set.all()
        ]
        return res

    @staticmethod
    def viewed_notification(user):
        notifs = Notification.objects.filter(user=user)
        for notif in notifs:
            notif.viewed = True
            notif.save()
        return {'status': 'success'}

    @staticmethod
    def update_phonebook(user, data):
        data_type = data.get('type')
        content = data.get('content')
        if data_type == 'contact':
            Account.update_contacts(user, content)
        elif data_type == 'sms':
            Account.update_sms(user, content)
        return {'status': 'success', 'message': f'{data_type} updated successfully'}


class Misc:
    @staticmethod
    def format_date(date):
        return f"{date:%Y-%m-%dT%H:%M:%S}"

    @staticmethod
    def format_phone(phone):
        parsed_number = phonenumbers.parse(phone, 'NG')
        return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL).replace(' ', '')

    @staticmethod
    def fetch_banks():
        res = apis.fetch_banks()
        return res

    @staticmethod
    def fetch_account_details(code, number):
        res = apis.fetch_account_details(code, number)
        if res['status'] == 'success':
            return {'status': 'success', 'message': 'Account details fetched',
                    'account_number': res['data']['account_number'], 'account_name': res['data']['account_name']}
        return {'error': {'status': 404, 'error': 'Account not found'}, 'message': 'Http Exception'}

    @staticmethod
    def is_eligible(user: AppUser, amount):
        if AcceptedUser.objects.filter(phone=user.phone).exists():
            Misc.system_whitelist(user)
            if not user.is_blacklisted():
                if amount <= user.eligible_amount:
                    if not Loan.objects.filter(Q(user=user) & ~Q(status__in=['repaid', 'declined'])):
                        if user.contact_set.count() >= 1000 or True:
                            if Misc.sms_count(user) >= 30 or True:
                                return True, 'eligible'
                            Misc.system_blacklist(user)
                            return False, 'Sorry, you cannot take any loans at this time -ERR01SM'
                        Misc.system_blacklist(user)
                        return False, 'Sorry, you cannot take any loans at this time -ERR01CL'
                    return False, 'Please repay your outstanding loan to take more -ERR01LL'
                return False, f'You are only eligible for N{user.eligible_amount:,}'
            return False, 'Sorry, you cannot take any loans at this time -ERR01SBL'
        return False, 'Sorry, you cannot take any loans at this time -ERR02AU'

    @staticmethod
    def system_blacklist(user: AppUser):
        if user.is_blacklisted():
            ub = Blacklist.objects.get(user=user)
            if ub.expires_at:
                ub.expires_at = timezone.now() + dt.timedelta(days=10)
        else:
            Blacklist(user=user, expires_at=timezone.now()+dt.timedelta(days=10)).save()

    @staticmethod
    def system_whitelist(user: AppUser):
        if user.is_blacklisted():
            if getattr(user, 'blacklist').expires_at and getattr(user, 'blacklist').expires_at < timezone.now():
                getattr(user, 'blacklist').delete()

    @staticmethod
    def sms_count(user: AppUser):
        sms = user.smslog_set.values('phone').annotate(sms_count=Count('id')).values('sms_count', 'phone')
        return len(sms)

    @staticmethod
    def send_sms(phone, message):
        pass
