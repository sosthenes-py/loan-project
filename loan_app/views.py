from django.shortcuts import render
from . import utils
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt


@csrf_exempt
def register(request):
    if request.method == 'POST':
        posted_data = {}
        for key, value in request.POST.items():
            posted_data[key] = value
        for key, value in request.FILES.items():
            posted_data[key] = value
        response = utils.Auth.create_account(**posted_data)
        return JsonResponse(response)


@csrf_exempt
def authenticate(request):
    if request.method == 'POST':
        response = utils.Auth.authenticate(phone=request.POST['phone'], password=request.POST['password'])
        return JsonResponse(response)


def is_phone_exist(request):
    if request.method == 'POST':
        return JsonResponse({'status': utils.Auth.is_phone_exist(request.POST['phone'])})
