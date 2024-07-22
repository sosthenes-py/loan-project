import json

from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt

from .forms import RegisterForm, LoginForm
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from .models import User
from django.contrib.auth.hashers import make_password
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from admin_panel.models import Repayment
import admin_panel.utils as utils
import datetime as dt


# Create your views here.
@login_required
def logout_user(request):
    logout(request)
    return redirect('login')


def login_user(request):
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(request, username=form.cleaned_data['phone'], password=form.cleaned_data['password'])
            if user:
                login(request, user)
                return JsonResponse({'status': 'success', 'message': 'User login successful'})
            return JsonResponse({'status': 'error', 'message': 'Invalid phone or password'})
        return JsonResponse({'status': 'warning', 'message': form.errors})
    else:
        form = LoginForm()
        return render(request, 'admin_panel/auth/login.html', {'form': form})


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            if not User.objects.filter(phone=form.cleaned_data['phone']).exists():
                user = form.save(commit=False)
                user.password = make_password(form.cleaned_data['password'])
                user.save()
                return JsonResponse({'status': 'success', 'message': 'User registered successfully!'})
            return JsonResponse({'status': 'error', 'message': 'Phone already registered!'})
        return JsonResponse({'status': 'warning', 'message': form.errors})
    else:
        form = RegisterForm()
        return render(request, 'admin_panel/auth/register.html', {'form': form})


@login_required
def dashboard(request):
    return render(request, 'admin_panel/dashboard.html')


@login_required
def users(request):
    if request.method == "GET":
        return render(request, 'admin_panel/users.html')
    posted_data = {}
    for key, value in request.POST.items():
        posted_data[key] = value
    response = utils.UserUtils(request, **posted_data)
    response.process()
    return JsonResponse({'status': response.status, 'content': response.content, 'message': response.message})


@login_required
def loans(request):
    if request.method == "GET":
        return render(request, 'admin_panel/loans.html')
    posted_data = {}
    for key, value in request.POST.items():
        posted_data[key] = value
    response = utils.LoanUtils(request, **posted_data)
    response.process()
    return JsonResponse({'status': response.status, 'content': response.content, 'message': response.message})


@login_required
def loans_with_status(request, status):
    if request.method == "GET":
        if status in ('pending', 'approved', 'declined', 'disbursed', 'overdue', 'partpayment', 'repaid'):
            return render(request, 'admin_panel/loan_with_status.html', {"status": status})
        return HttpResponseBadRequest(status=404)


@login_required
def repayments(request):
    if request.method == "GET":
        return render(request, 'admin_panel/repayments.html')
    posted_data = {}
    for key, value in request.POST.items():
        posted_data[key] = value
    response = utils.LoanUtils(request, **posted_data)
    response.process()
    print(response.status)
    return JsonResponse({'status': response.status, 'content': response.content, 'message': response.message})


@login_required
def waiver(request):
    return render(request, 'admin_panel/waiver.html')


@login_required
def view_blacklist(request):
    return render(request, 'admin_panel/blacklist.html')


@login_required
def view_logs(request):
    return render(request, 'admin_panel/logs.html')


@login_required
def accepted_users(request):
    return render(request, 'admin_panel/accepted_user.html')


@login_required
def analysis(request):
    if request.method == "GET":
        return render(request, 'admin_panel/analysis.html')
    action = request.POST.get('action')
    if action == "get_analysis":
        fetch = request.POST.get('fetch', 'rda').split(',')
        content = {}
        analysis_ = utils.Analysis(request.user)
        if 'rda' in fetch:
            analysis_.real_day(request.POST.get('date', '2024-5'))
            analysis_.generate_chart(_for='real_day')
            content['rda'] = analysis_.content
        if 'rdp' in fetch:
            progressive = analysis_.progressive(
                start=request.POST.get('rdp_start', '2024-5-1'),
                end=request.POST.get('rdp_end', f'{dt.date.today():%Y-%m-%d}'),
                dimension=request.POST.get('rdp_dimension', 'count'),
                loan_type=request.POST.get('rdp_loan_type', 'all')
            )
            content['rdp'] = progressive
        if 'cda' in fetch:
            cda = analysis_.get_collections(
                start=request.POST.get('cda_start', '2024-5-1'),
                end=request.POST.get('cda_end', f'{dt.date.today():%Y-%m-%d}'),
                stage=request.POST.get('cda_stage', 'S-1,S0,S1,S2,S3,S4,M1')
            )
            content['cda'] = cda
        if 'crc' in fetch:
            crc = analysis_.collection_rates_chart()
            content['crc'] = crc
    elif action == 'fetch_dashboard':
        content = {}
        analysis_ = utils.Analysis(request.user)
        obtain_list = ['pending', 'disbursed', 'repaid', 'declined']
        for obtain in obtain_list:
            content[obtain] = analysis_.generate_data(
                _for=f'{obtain}',
                fetch=request.POST.get('fetch', 'amount')
            )
        content['dashboard'] = analysis_.get_dashboard(
            start=request.POST.get('start', '2024--1'),
            end=request.POST.get('end', f'{dt.date.today():%Y-%m-%d}')
        )
    elif action == 'fetch_main_bal':
        analysis_ = utils.Analysis(request.user)
        content = analysis_.fetch_main_balance()
    return JsonResponse({'status': 'success', 'content': content})


@login_required
def operators(request):
    if request.method == "GET":
        return render(request, 'admin_panel/operators.html')
    posted_data = {}
    for key, value in request.POST.items():
        posted_data[key] = value
    response = utils.AdminUtils(request, **posted_data)
    response.process()
    return JsonResponse({'status': response.status, 'content': response.content, 'message': response.message})


@csrf_exempt
def webhook(request):
    secret_hash = 'mysecrethash'
    signature = request.headers.get("verif-hash")
    if signature or (signature != secret_hash):
        return HttpResponse(status=401)

    payload = json.loads(request.body)
    event = payload.get('event')
    data = payload.get('data')
    handler = utils.Func.webhook(event, data)
    return HttpResponse(status=200)


@csrf_exempt
def automations(request, program):
    if request.method == "GET":
        hour = dt.datetime.now().hour
        if program == 'progressive' and hour >= 23:
            utils.Func.set_progressive()
        elif program == 'collection' and hour == 0:
            utils.Func.set_collectors()
        elif program == 'recovery':
            utils.Func.set_recovery()
        return JsonResponse({'status': 'success'})
