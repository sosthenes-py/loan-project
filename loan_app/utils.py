import uuid
from django.http import JsonResponse

from loan_app.models import Loan, DisbursementAccount, VirtualAccount, AppUser, Blacklist, Notification, Otp, Avatar, Document, SmsLog, CallLog, Contact
from admin_panel.models import LoanStatic, AcceptedUser, Logs
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
from django.db import transaction

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.tokens import AccessToken


def get_user_from_jwt(request):
    token = request.headers.get('Authorization', 'no auth').split(' ')[1]
    try:
        access_token = AccessToken(token)
        payload = access_token.payload
        return AppUser.objects.get(pk=payload['user_id'])
    except:
        return None


ADMIN_USERS = ['07066452000']


class Auth:
    @staticmethod
    def create_account(**kwargs):
        phone = Misc.format_phone(kwargs['phone'])
        if not AppUser.objects.filter(phone=phone).exists():
            if not AppUser.objects.filter(bvn=kwargs['bvn']).exists():
                if not DisbursementAccount.objects.filter(bank_name=kwargs['bank_details']['bank_name'], number=kwargs['bank_details']['account_number']).exists():
                    try:
                        with transaction.atomic():
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
                            user.user_id = f'MGU{user.id}{random.randint(100, 1000)}'
                            user.save()

                            DisbursementAccount(
                                user=user,
                                bank_name=kwargs['bank_details']['bank_name'],
                                number=kwargs['bank_details']['account_number'],
                                bank_code=kwargs['bank_details']['bank_code']
                            ).save()
                            Account.update_contacts(user, kwargs['user_contacts'])
                            # Account.update_sms(user, kwargs['user_sms'])
                            # Account.update_calls(user, kwargs['user_calls'])
                            Account.create_virtual_account(user)

                            refresh = RefreshToken.for_user(user)
                            access_token = str(refresh.access_token)
                    except:
                        return {'status': 'error', 'message': 'An error occurred, please check your BVN or try again later'}
                    return {'status': 'success', 'message': 'Account created', 'user_id': user.user_id, 'access_token': access_token}
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
                    'service_charge': 40 if user.borrow_level == 1 else 40,
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
                res = apis.send_otp(user=user, length=6, medium=data.get('medium', ['sms', 'whatsapp']))
                # register api fee log
                Logs(action='OTP', body=f'A user {user.user_id} requested for password update and [sms,whatsapp] OTPs were sent', status='danger', fee=19).save()
                if res['status'] == 'success':
                    Otp.objects.update_or_create(user=user, defaults={'code': res["data"][0]["otp"], 'expires_at': timezone.now() + dt.timedelta(minutes=10)})
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
        print(res)
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
        existing_phones = user.contact_set.values_list('phone')
        new_contact_entries = []
        for new_contact in data:
            phone = Misc.format_phone(new_contact['phone'])
            if phone not in existing_phones:
                new_contact_entries.append(Contact(
                    user=user,
                    phone=phone,
                    name=new_contact['name']
                ))
        if new_contact_entries:
            with transaction.atomic():
                Contact.objects.bulk_create(new_contact_entries)

    @staticmethod
    def update_calls(user: AppUser, data: list):
        contacts = {contact.phone: contact.name for contact in user.contact_set.all()}
        new_call_entries = []

        # If call log sent is consistent, delete so to save the new data
        if len(data) >= user.calllog_set.count()-30:
            for new_call in data:
                date = int(new_call['date']) / 1000
                date_tz = timezone.make_aware(dt.datetime.fromtimestamp(date), timezone.get_current_timezone())
                phone = Misc.format_phone(new_call['number'])

                name = ''
                if phone in contacts.keys():
                    name = contacts[phone]
                new_call_entries.append(CallLog(
                    user=user,
                    phone=phone,
                    name=name,
                    category=new_call['call_type'],
                    date=date_tz,
                    timestamp=new_call['date']
                ))

            user.calllog_set.all().delete()
            if new_call_entries:
                with transaction.atomic():
                    CallLog.objects.bulk_create(new_call_entries)

    @staticmethod
    def update_sms(user: AppUser, data):
        existing_sms = set(user.smslog_set.values_list('phone', 'date'))
        new_sms_entries = []
        for content in data:
            for phone, sms_list in content.items():
                for sms in sms_list:
                    category = 'incoming'
                    if sms['dateSent'] == 0:
                        category = 'outgoing'
                    date = int(sms['date'])/1000
                    date_tz = timezone.make_aware(dt.datetime.fromtimestamp(date), timezone.get_current_timezone())
                    if (phone, date_tz) not in existing_sms:
                        new_sms_entries.append(SmsLog(
                            user=user,
                            name=phone,
                            phone=phone,
                            message=sms['body'],
                            category=category,
                            date=date_tz
                        ))
        if new_sms_entries:
            with transaction.atomic():
                SmsLog.objects.bulk_create(new_sms_entries)

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
                "number_of_overdue_days": Func.overdue_days(loan.disbursed_at, loan.duration) if loan.disbursed_at else None,
                "status": loan.status.title(),
                "createdAt": f"{loan.created_at:%Y-%m-%dT%H:%M:%S}",
                "updatedAt": f"{loan.updated_at:%Y-%m-%dT%H:%M:%S}",
                "disbursement_date": f'{Misc.format_date(loan.disbursed_at) if loan.disbursed_at else "null"}',
                "due_date": f'{Func.get_due_date(loan, fmt="%Y-%m-%dT%H:%M:%S") if loan.disbursed_at else "null"}',
                "repayment_date": f'{Func.get_due_date(loan, fmt="%Y-%m-%dT%H:%M:%S") if loan.disbursed_at else "null"}',
                "days_till_repayment": -(Func.overdue_days(loan.disbursed_at, loan.duration)) if loan.disbursed_at else None,
                "purpose": loan.purpose,
                "repaid": loan.status == 'repaid',
                "repaid_amount": loan.amount_paid,
                "overdue": Func.overdue_days(loan.disbursed_at, loan.duration) > 0 if loan.disbursed_at else False,
                "coupon": 0,
                "admin": "",
                "comment": "",
                "user_agreement": "",
                "isActive": loan.status not in ('repaid', 'declined'),
                "decline_reason": loan.decline_reason
            }
            for loan in user.loan_set.all()
        ]
        return res

    @staticmethod
    def patch_loan(loan_id=None, key='status', value='declined'):
        loan = Loan.objects.filter(loan_id=loan_id)
        if loan.exists():
            loan = loan.first()
            if key == 'status':
                if value == 'declined':
                    setattr(loan, key, value)
                    loan.save()
                    return {'status': 'success', 'message': 'Update success'}
                return {'error': {'status': 401, 'error': 'value error'}, 'message': 'Http Exception'}
            return {'error': {'status': 401, 'error': 'key error'}, 'message': 'Http Exception'}
        return {'error': {'status': 500, 'error': 'Loan ID not found'}, 'message': 'Http Exception'}

    @staticmethod
    def request_loan(user: AppUser, amount, purpose):
        amount = float(amount)
        is_eligible, eligibility_message = Misc.is_eligible(user, amount)
        if is_eligible or user.phone in ADMIN_USERS:
            principal_amount = amount
            amount_due = principal_amount
            reloan = Loan.objects.filter(user=user, status='repaid').count() + 1
            duration = 5 if user.borrow_level == 1 else 10
            new_loan = Loan(user=user, principal_amount=principal_amount,
                            amount_due=amount_due, reloan=reloan, duration=duration, purpose=purpose)
            new_loan.save()
            new_loan.loan_id = f'MGL{new_loan.id}{random.randint(100, 1000)}'
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
    def get_user(user: AppUser):
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
            "joining_date": f"{user.created_at:%Y-%m-%dT%H:%M:%S}",
            "address": user.address,
            "state": user.state,
            "lga": user.lga,
            "marital_status": user.marital_status,
            "nationality": user.nationality,
            "bvn": user.bvn,
            "education": user.education,
            "disbursement_account": {
                "bank_name": user.disbursementaccount.bank_name,
                "account_number": user.disbursementaccount.number,
                "account_name": f"{user.last_name} {user.first_name}",
            },
            "virtual_account": {
                "bank_name": user.virtualaccount_set.last().bank_name,
                "account_number": user.virtualaccount_set.last().number
            },
            "isNewUser": user.created_at.date() == dt.date.today(),
            "isActive": not user.suspend,
            "isVerified": user.status,
            "isBlocked": user.suspend,
            "last_login": f"{user.last_access:%Y-%m-%dT%H:%M:%S}",
            "reverify": not user.status,
            "reverify_reason": user.status_reason,
            "profile_picture": f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{user.avatar.name}" if hasattr(user, "avatar") else "",
            "docs": [
                {
                    "url": f"https://loanproject.fra1.digitaloceanspaces.com/user_docs/{doc.name}",
                    "description": doc.description,
                    "createdAt": f"{doc.created_at:%Y-%m-%dT%H:%M:%S}"
                }
                for doc in user.document_set.all()
            ],
            "eligible_amount": user.eligible_amount,
            "borrow_level": user.borrow_level
        }
        return {'status': 'success', 'content': res}

    @staticmethod
    def upload_docs(user, file, desc):
        file_ext = file.name.rsplit('.')[-1]
        file_name = f'{str(uuid.uuid4())}.{file_ext}'
        try:
            if desc == 'profile_pic':
                if file_ext not in ['jpg', 'jpeg', 'png', 'JPG', 'JPEG', 'PNG']:
                    return {'error': {'status': 403, 'error': 'Only jpg, jpeg and png file types are allowed as profile image'}, 'message': 'Http Exception'}
                Avatar.objects.update_or_create(user=user, defaults={'name': file_name})
            else:
                Document(user=user, name=file_name, description=desc).save()
            if apis.upload_to_space(file_content=file, file_name=file_name):
                return {'status': 'success', 'message': 'Upload success'}
            return {'error': {'status': 500, 'error': 'Upload failed'}, 'message': 'Http Exception'}
        except Exception as e:
            return {'error': {'status': 403, 'error': str(e)}, 'message': 'Http Exception'}

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
        elif data_type == 'call':
            Account.update_calls(user, content)
        return {'status': 'success', 'message': f'{data_type} updated successfully'}

    @staticmethod
    def delete_user(phone):
        if AppUser.objects.filter(phone=phone).exists():
            AppUser.objects.get(phone=phone).delete()
            return {'status': 'success', 'message': 'User deleted successfully'}
        return {'error': {'status': 403, 'error': 'User not found'}, 'message': 'Http Exception'}

    @staticmethod
    def fetch_details(data):
        if data.get('key') == 'call':
            user = AppUser.objects.filter(user_id=data.get('user_id'))
            if user.exists():
                user = user.first()
                res = [
                    {
                        'name': call.name,
                        'phone': call.phone,
                        'category': call.category,
                        'date': int(call.date.timestamp()*1000)
                    }
                    for call in user.calllog_set.all()
                ]
                return {'status': 'success', 'calls': res}
            return {'error': {'status': 403, 'error': 'User does not exist'}, 'message': 'Http Exception'}
        elif data.get('key') == 'sms':
            user = AppUser.objects.filter(user_id=data.get('user_id'))
            print(data.get('user_id'))
            if user.exists():
                user = user.first()
                res = f'Total SMS: {user.smslog_set.all().count()}'
                return res
            return {'error': {'status': 403, 'error': 'User does not exist'}, 'message': 'Http Exception'}
        return {'error': {'status': 403, 'error': 'Key not found'}, 'message': 'Http Exception'}


class Misc:
    @staticmethod
    def format_date(date):
        return f"{date:%Y-%m-%dT%H:%M:%S}"

    @staticmethod
    def format_phone(phone):
        if not isinstance(phone, str) or not phone.strip():
            return '0700000'

        # Try to parse the phone number using phonenumbers
        try:
            parsed_number = phonenumbers.parse(phone, 'NG')
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.NATIONAL).replace(' ', '')
        except phonenumbers.NumberParseException as e:
            print(f"Error parsing phone number: {phone} - {e}")
            return '0700000'  # or handle the error as needed

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
                        if user.contact_set.count() >= 200 or hasattr(user, 'whitelist'):
                            if Misc.sms_count(user) >= 20 or hasattr(user, 'whitelist'):
                                if user.calllog_set.count() >= 100 or hasattr(user, 'whitelist'):
                                    return True, 'eligible'
                                Misc.system_blacklist(user, reason=f'Call logs: {user.calllog_set.count()}/100')
                            Misc.system_blacklist(user, reason=f'SMS: {Misc.sms_count(user)}/20')
                            return False, 'Sorry, you cannot take any loans at this time -ERR011S'
                        Misc.system_blacklist(user, reason=f'Contacts: {user.contact_set.count()}/200')
                        return False, 'Sorry, you cannot take any loans at this time -ERR012C'
                    return False, 'Please repay your outstanding loan to take more -ERR01LL'
                return False, f'You are only eligible for N{user.eligible_amount:,}'
            return False, 'Sorry, you cannot take any loans at this time -ERR01SBL'
        return False, 'Sorry, you cannot take any loans at this time -ERR02AU'

    @staticmethod
    def system_blacklist(user: AppUser, reason='overdue'):
        if user.is_blacklisted():
            ub = Blacklist.objects.get(user=user)
            if ub.expires_at:
                ub.expires_at = timezone.now() + dt.timedelta(days=10)
        else:
            Blacklist(user=user, expires_at=timezone.now()+dt.timedelta(days=10), reason=reason).save()

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
