# TODO: set back fetch virtual accounts to use flw api

import json
import datetime as dt
from decouple import config
import requests
from rave_python import Rave
import boto3
from botocore.exceptions import NoCredentialsError

NUBAN_API_KEY = config('NUBAN_API_KEY')
RAVE_PUBLIC_KEY = config('RAVE_PUBLIC_KEY')
RAVE_PRIVATE_KEY = config('RAVE_SECRET_KEY')
SPACE_ACCESS_KEY = config('SPACE_ACCESS_KEY')
SPACE_SECRET_KEY = config('SPACE_SECRET_KEY')
SPACE_NAME = 'user_docs'


def fetch_account_details(code, number):
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }
    data = {
        'account_number': number,
        'account_bank': code
    }
    url = f'https://api.flutterwave.com/v3/accounts/resolve'
    res = requests.post(url=url, headers=headers, data=data)
    return res.json()


# rave = Rave(RAVE_PUBLIC_KEY, RAVE_PRIVATE_KEY, usingEnv=False)


def generate_flw_virtual_account(user):
    """

    :param user:
    :return: {'status': 'success', 'message': 'Virtual account created', 'data': {'response_code': '02', 'response_message': 'Transaction in progress', 'flw_ref': 'FLW-09f3e0346631410c81cc5c6405ae629c', 'order_ref': 'URF_1721241565959_891435', 'account_number': '8548254586', 'frequency': 'N/A', 'bank_name': 'WEMA BANK', 'created_at': '2024-07-17 18:39:26', 'expiry_date': 'N/A', 'note': 'Please make a bank transfer to Narration FLW', 'amount': '0.00'}}

    """
    data = {
        'email': user.email,
        'is_permanent': True,
        'bvn': user.bvn,
        'firstname': user.first_name,
        'lastname': user.last_name,
        'phonenumber': user.phone,
        'narration': f'MGLoan-{user.last_name}',
        'tx_ref': 'mgloan'
    }
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }

    url = 'https://api.flutterwave.com/v3/virtual-account-numbers'
    res = requests.post(url=url, headers=headers, data=data)
    return res.json()


def is_tx_valid(id_):
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }
    url = f'https://api.flutterwave.com/v3/transactions/{id_}/verify'
    res = requests.get(url=url, headers=headers)
    return res.json()['status'] == 'success'


bb = [
    {
        'bank_code': '057',
        'account_number': '2118728610',
        # 'amount': loan.principal_amount - ((loan.interest_perc / 100) * loan.principal_amount),
        'amount': 1000,
        'currency': 'NGN',
        'narration': 'MG Loan',
        'reference': f'MGL1234-2',
        'meta': [
            {
                'email': 'sos.sosthenes1@gmail.com',
                'server': 'mgloan'
            }
        ]

    }
]


def create_bulk_tf(bdata, admin_user):
    data = {
        'title': f"Disb by {admin_user.level} - {admin_user.first_name}",
        'bulk_data': bdata
    }
    data = json.dumps(data)
    url = 'https://api.flutterwave.com/v3/bulk-transfers'

    if len(bdata) == 1:
        dd = bdata[0]
        data = {
            "account_bank": dd['bank_code'],
            "account_number": dd['account_number'],
            "amount": dd['amount'],
            "narration": dd['narration'],
            "currency": "NGN",
            "reference": dd['reference'],
            "debit_currency": "NGN"
        }
        url = 'https://api.flutterwave.com/v3/transfers'

    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}',
        'content-type': 'application/json',
    }
    print(f'Data--------------{data}')
    res = requests.post(url=url, headers=headers, data=json.dumps(data))
    print(res.json())
    return res.json()


def create_tf():
    data = {
        'title': f"Disb by test",
        'bulk_data': bb
    }

    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}',
        'content-type': 'application/json',
    }
    url = 'https://api.flutterwave.com/v3/bulk-transfers'
    res = requests.post(url=url, headers=headers, data=json.dumps(data))
    print(res.json())
    return res.json()




def fetch_main_bal():
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }
    url = f'https://api.flutterwave.com/v3/balances/NGN'
    res = requests.get(url=url, headers=headers)
    res = res.json()
    if res['status'] == 'success':
        return float(res['data']['available_balance'])
    else:
        return 0


def fetch_banks():
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }

    url = f'https://api.flutterwave.com/v3/banks/NG'
    res = requests.get(url=url, headers=headers)
    return res.json()


def send_otp(user, length, medium: list):
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }
    data = {
        'length': length,
        'sender': 'MGLOAN',
        'send': False,
        'medium': medium,
        'expiry': 10,
        'customer': {
            'name': f'{user.last_name} {user.first_name}',
            'phone': user.phone,
            'email': user.email
        }
    }

    url = f'https://api.flutterwave.com/v3/otps'
    res = requests.post(url=url, headers=headers, json=data)
    return res.json()


def send():
    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}'
    }
    data = {
        'length': 6,
        'customer': {
            'name': 'Onyeka',
            'email': 'sos.sosthenes1@gmail.com',
            'phone': '2348147173448'
        },
        'sender': 'MGLOAN',
        'send': True,
        'medium': ['whatsapp'],
        'expiry': 10,
    }

    url = f'https://api.flutterwave.com/v3/otps'
    res = requests.post(url=url, headers=headers, data=data)
    return res.json()


def upload_to_space(file_content, file_name, space_name=SPACE_NAME, aws_access_key_id=SPACE_ACCESS_KEY, aws_secret_access_key=SPACE_SECRET_KEY):
    try:
        # Create an S3 client
        s3 = boto3.client('s3', endpoint_url='https://loanproject.fra1.digitaloceanspaces.com',
                          aws_access_key_id=aws_access_key_id,
                          aws_secret_access_key=aws_secret_access_key)

        object_key = file_name
        # Upload the file
        s3.upload_fileobj(file_content, space_name, object_key, ExtraArgs={'ACL': 'public-read'})

        print(f"File {file_name} uploaded to {space_name} successfully.")
        return True

    except NoCredentialsError:
        print("Credentials not available.")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False


def delete_from_space(file_name, space_name=SPACE_NAME, aws_access_key_id=SPACE_ACCESS_KEY, aws_secret_access_key=SPACE_SECRET_KEY):
    try:
        # Create an S3 client
        s3 = boto3.client('s3', endpoint_url='https://loanproject.fra1.digitaloceanspaces.com',
                          aws_access_key_id=aws_access_key_id,
                          aws_secret_access_key=aws_secret_access_key)

        object_key = file_name

        # Delete the file from the space
        s3.delete_object(Bucket=space_name, Key=object_key)

        print(f"File {file_name} deleted from {space_name} successfully.")
        return True

    except NoCredentialsError:
        print("Credentials not available.")
        return False
    except Exception as e:
        print(f"An error occurred: {e}")
        return False
