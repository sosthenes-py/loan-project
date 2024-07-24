import json
from . import utils
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from decouple import config
from django.http import HttpResponse


@csrf_exempt
def register(request):
    if request.method == 'POST':
        posted_data = {}
        data = json.loads(request.body)
        for key, value in data.items():
            posted_data[key] = value
        response = utils.Auth.create_account(**posted_data)
        return JsonResponse(response)


@csrf_exempt
def authenticate(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')
            return utils.Auth.authenticate_user(username, password)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def change_password(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'POST':
            try:
                data = json.loads(request.body)
                old_password = data.get('old_password')
                new_password = data.get('password')
                return JsonResponse(utils.Auth.change_password(user, old_password=old_password, new_password=new_password))
            except json.JSONDecodeError:
                return JsonResponse({'error': 'Invalid JSON'}, status=400)
        return JsonResponse({'error': 'Invalid method'}, status=405)
    return JsonResponse({'error': {'status': 401, 'error': 'User not found or Invalid token'}, 'message': 'Http Exception'})


@csrf_exempt
def update_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        return JsonResponse(utils.Auth.update_password(data))
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def fetch_account_details(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            bank_code = data.get('bank_code')
            account_number = data.get('account_number')
            return JsonResponse(utils.Misc.fetch_account_details(code=bank_code, number=account_number))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def fetch_banks(request):
    if request.method == 'GET':
        return JsonResponse(utils.Misc.fetch_banks())
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def loans(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'GET':
            return JsonResponse({'loans': utils.Account.fetch_loans(user)}, safe=False)
        elif request.method == 'POST':
            data = json.loads(request.body)
            amount = data.get('amount')
            purpose = data.get('purpose')
            return JsonResponse(utils.Account.request_loan(user, amount, purpose), safe=False)
    return JsonResponse({'error': {'status': 401, 'error': 'User not found or Invalid token'}, 'message': 'Http Exception'})


@csrf_exempt
def get_user(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'GET':
            return JsonResponse(utils.Account.get_user(user))
        return JsonResponse({'error': 'Invalid method'}, status=405)
    return JsonResponse(
        {'error': {'status': 401, 'error': 'User not found or Invalid token'}, 'message': 'Http Exception'})


@csrf_exempt
def docs(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'POST':
            try:
                if request.content_type.startswith('multipart/form-data'):
                    desc = request.POST.get('description')
                    file = request.FILES['file']
                    response_data = utils.Account.upload_docs(user, file, desc)
                    return JsonResponse(response_data)
                else:
                    return JsonResponse({'error': 'Invalid content type'}, status=400)
            except Exception as e:
                return JsonResponse({'error': str(e)}, status=500)
        else:
            return JsonResponse({'error': 'Invalid method'}, status=405)
    return JsonResponse({'error': 'User not found or Invalid token'}, status=401)


@csrf_exempt
def notifications(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'GET':
            return JsonResponse(utils.Account.fetch_notifications(user), safe=False)
        else:
            return JsonResponse(utils.Account.viewed_notification(user))


@csrf_exempt
def update_phonebook(request):
    user = utils.get_user_from_jwt(request)
    if user:
        if request.method == 'POST':
            data = json.loads(request.body)
            return JsonResponse(utils.Account.update_phonebook(user, data), safe=False)
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    return JsonResponse(
        {'error': {'status': 401, 'error': 'User not found or Invalid token'}, 'message': 'Http Exception'})


@csrf_exempt
def delete_user(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        if data['passcode'] == config('APP_SECRET_CODE'):
            return JsonResponse(utils.Account.delete_user(data['phone']))
        return JsonResponse({'error': 'Invalid passcode'}, status=405)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@csrf_exempt
def pick_a_link(request, option):
    if option == '77ea6d6bbdb1':
        res = 'A 4 days trip to Lagos with me!'
    elif option == '40uqmwjppoan':
        res = 'A good sum of money wil be deposited to your account on Aug 1'
    elif option == '46ufcvbjddhqq':
        res = 'Take you out for a very nice cloth shopping'
    elif option == '28efvbnkhgyfj':
        res = 'Get you only 1 expensive wig of your choice'
    elif option == '52pjkhvcgccfb':
        res = 'Come to my place and prepare me 1 unique meal per day for one week'
    elif option == '34rgvndjghvjkn':
        res = 'You now have 3 chances!'
    elif option == '12ugjbvdfujbvo':
        res = 'Take you to a fanciful place in Enugu'
    else:
        res = 'nothing'
    utils.Misc.nwam(res)
    return HttpResponse(f'<h1>{res}</h1>')
