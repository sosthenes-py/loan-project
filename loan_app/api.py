import json
import datetime as dt
import os

import requests
from rave_python import Rave

NUBAN_API_KEY = os.environ.get('NUBAN_API_KEY')
RAVE_PUBLIC_KEY = os.environ.get('RAVE_PUBLIC_KEY')
RAVE_PRIVATE_KEY = os.environ.get('RAVE_PRIVATE_KEY')


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


rave = Rave(RAVE_PUBLIC_KEY, RAVE_PRIVATE_KEY, usingEnv=True)


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
        'narration': f'SportyCredit-{user.last_name}'
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


def create_bulk_tf(bdata, admin_user):
    data = {
        'title': f"Disb by {admin_user.level} - {admin_user.first_name} @ {dt.datetime.now():%b %d, %Y}",
        'bulk_data': bdata
    }

    headers = {
        'Authorization': f'Bearer {RAVE_PRIVATE_KEY}',
        'content-type': 'application/json',
    }
    url = 'https://api.flutterwave.com/v3/bulk-transfers'
    res = requests.post(url=url, headers=headers, data=json.dumps(data))
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
        'sender': 'SportyCredit',
        'send': True,
        'medium': medium,
        'expiry': 10,
        'customer': {
            'name': f'{user.last_name} {user.first_name}',
            'phone': user.phone,
            'email': user.email
        }
    }

    url = f'https://api.flutterwave.com/v3/otps'
    res = requests.post(url=url, headers=headers, data=data)
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
        'sender': 'SportyCredit',
        'send': True,
        'medium': ['whatsapp'],
        'expiry': 10,
    }

    url = f'https://api.flutterwave.com/v3/otps'
    res = requests.post(url=url, headers=headers, data=data)
    return res.json()


# print(send())
