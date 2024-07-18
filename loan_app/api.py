import json
import datetime as dt
import requests
from rave_python import Rave

NUBAN_API_KEY = 'NUBAN-RKYBIBGC2163'
RAVE_PUBLIC_KEY = 'FLWPUBK-f253ac8668d214bfe067855e421cb9ae-X'
RAVE_PRIVATE_KEY = 'FLWSECK-90c21d061b428e59ab438e962c507d74-190c239b6e6vt-X'


def get_account_details(bank_code, acc_no):
    params = {
        'bank_code': bank_code,
        'acc_no': acc_no
    }
    response = requests.get(url=f'https://app.nuban.com.ng/api/{NUBAN_API_KEY}', params=params)
    return response.json()


rave = Rave(RAVE_PUBLIC_KEY, RAVE_PRIVATE_KEY, usingEnv=False)


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
