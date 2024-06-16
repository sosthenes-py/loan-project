from loan_app.models import Loan, Document, Avatar, DisbursementAccount, VirtualAccount, AppUser
from django.contrib.auth.hashers import make_password, check_password
import random
from django.utils import timezone
import datetime as dt
from faker import Faker
from django.db.models import Q
from project_pack.models import Project


class Auth:
    @staticmethod
    def create_account(**kwargs):
        if not AppUser.objects.filter(phone=kwargs['phone']).exists():
            user = AppUser(
                first_name=kwargs['first_name'],
                last_name=kwargs['last_name'],
                middle_name=kwargs.get('middle_name'),
                email=kwargs['email'],
                password=make_password(kwargs['password']),
                phone=kwargs['phone'],
                bvn=kwargs['bvn'],
                address=kwargs['address'],
                dob=dt.datetime.strptime(kwargs['dob'], '%Y-%m-%d'),
                gender=kwargs['gender']
            )
            user.save()
            user.user_id = f'SU{user.id}{random.randint(100, 1000)}'
            user.save()

            if kwargs.get('file'):
                Document(
                    user=user,
                    file=kwargs.get('file'),
                    description='User ID',
                ).save()

            if kwargs.get('avatar'):
                Avatar(
                    user=user,
                    file=kwargs.get('avatar'),
                ).save()

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
                bank_name=kwargs['bank_name'],
                number=kwargs['bank_number']
            ).save()
            Account.create_virtual_account(user)
            return {'user_id': user.user_id, 'status': 'success', 'message': 'Account created'}
        return {'status': 'error', 'message': 'Phone already exists'}

    @staticmethod
    def is_phone_exist(phone):
        return AppUser.objects.filter(phone=phone).exists()

    @staticmethod
    def authenticate(phone, password):
        if AppUser.objects.filter(phone=phone).exists():
            user = AppUser.objects.get(phone=phone)
            if check_password(password, user.password):
                return {'status': 'success', 'message': 'Login successful', 'user_id': user.user_id, 'first_name': user.first_name, 'last_name': user.last_name, 'created_at': f'{user.created_at:%Y-%m-%d}'}
            return {'status': 'error', 'message': 'Password incorrect'}
        return {'status': 'error', 'message': 'Phone does not exist'}


class Account:
    @staticmethod
    def create_virtual_account(user: AppUser):
        # After creating virtual account, store to db
        bank_number = 2116038168
        bank_name = 'UBA'
        bank_code = 145
        VirtualAccount(user=user, number=bank_number, bank_name=bank_name, bank_code=bank_code).save()

    @staticmethod
    def request_loan(user_id, amount):
        user = AppUser.objects.get(user_id=user_id)
        amount = float(amount)
        is_eligible, eligibility_message = Account.is_eligible(user, amount)
        if is_eligible:
            principal_amount = amount
            amount_due = principal_amount
            reloan = Loan.objects.filter(user=user, status='repaid').count() + 1
            new_loan = Loan(user=user, principal_amount=principal_amount,
                            amount_due=amount_due, reloan=reloan)
            new_loan.save()
            new_loan.loan_id = f'SL{new_loan.id}{random.randint(100, 1000)}'
            new_loan.save()
            return {'status': 'success', 'message': 'Loan submitted successfully'}
        return {'status': 'error', 'message': eligibility_message}

    @staticmethod
    def is_eligible(user: AppUser, amount):
        if user.status:
            if amount <= user.eligible_amount:
                if not Loan.objects.filter(Q(user=user) & ~Q(status__in=['repaid', 'declined'])):
                    return True, 'eligible'
                return False, 'Please repay your outstanding loan to take more'
            return False, f'You are only eligible for #{user.eligible_amount}'
        return False, 'Sorry, you cannot take any loans at this time'

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
