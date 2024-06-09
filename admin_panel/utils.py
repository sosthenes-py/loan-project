import django.db.models
from django.db.models import Sum
from django.utils import timezone
import datetime as dt
from django.db.models import Sum, Count, Case, When, Value, F, DecimalField, Q
from django.db.models.functions import TruncDay
from calendar import monthrange
import random
import math

from .models import User as AdminUser, AdminLog, Note, Collection, LoanStatic, Repayment, Progressive, Waive, Timeline
from loan_app.models import AppUser, Document, Emergency, Employment, DisbursementAccount, Loan
LOAN_DURATION = 6


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
                             end=f'{dt.date.today():%Y-%m-%d}'
                             ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d')
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        self.users = AppUser.objects.filter(created_at__gte=start_date, created_at__lte=end_date).order_by(
                '-created_at').all()
        self._content = ''
        for self.user in self.users[:int(rows)]:
            avatar = ''
            try:
                if self.user.avatar is not None:
                    avatar = self.user.avatar.file.url
            except:
                avatar = '/static/admin_panel/images/avatars/user.png'
            employment_content = ''
            employment_fields = self.user.employment._meta.get_fields()
            for employment_col in employment_fields:
                if employment_col.name != 'id' and employment_col.name != 'user':
                    employment_content += (f'data-employment_{employment_col.name}'
                                           f'={getattr(self.user.employment, employment_col.name)}')

            emergency_content = ''
            emergency_fields = self.user.emergency._meta.get_fields()
            for emergency_col in emergency_fields:
                if emergency_col.name != 'id' and emergency_col.name != 'user':
                    emergency_content += (f'data-emergency_{emergency_col.name}'
                                          f'={getattr(self.user.emergency, emergency_col.name)}')

            self.add_table_content(_for='all_users_table', avatar=avatar)

    def fetch_other_details(self):
        self._content = {}
        employment_fields = self.user.employment._meta.get_fields()
        for employment_col in employment_fields:
            if employment_col.name != 'id' and employment_col.name != 'user':
                self._content[f'employment_{employment_col.name}'] = getattr(self.user.employment, employment_col.name)

        emergency_fields = self.user.emergency._meta.get_fields()
        for emergency_col in emergency_fields:
            if emergency_col.name != 'id' and emergency_col.name != 'user':
                self._content[f'emergency_{emergency_col.name}'] = getattr(self.user.emergency, emergency_col.name)

        guarantor_fields = self.user.guarantor_set.all()[0]._meta.get_fields()
        for guarantor_col in guarantor_fields:
            if guarantor_col.name != 'id' and guarantor_col.name != 'user':
                self._content[f'guarantor_{guarantor_col.name}1'] = getattr(self.user.guarantor_set.all()[0],
                                                                            guarantor_col.name)

        guarantor_fields = self.user.guarantor_set.all()[1]._meta.get_fields()
        for guarantor_col in guarantor_fields:
            if guarantor_col.name != 'id' and guarantor_col.name != 'user':
                self._content[f'guarantor_{guarantor_col.name}2'] = getattr(self.user.guarantor_set.all()[1],
                                                                            guarantor_col.name)

        self._content['bankdetails_number'] = self.user.disbursementaccount.number
        self._content['bankdetails_bank'] = self.user.disbursementaccount.bank_name
        self._content['bankdetails_name'] = f'{self.user.last_name} {self.user.first_name}'
        self._content['bankdetails_bvn'] = self.user.bvn

        self._content['virtual_bankdetails_number'] = self.user.virtualaccount.number
        self._content['virtual_bankdetails_bank'] = self.user.virtualaccount.bank_name
        self._content['virtual_bankdetails_name'] = f'{self.user.last_name} {self.user.first_name}'

        self._content['loan_count'] = self.user.loan_set.count()
        self._content['repayment_count'] = self.user.repayment_set.count()
        self._content['notes_count'] = self.user.note_set.count()
        self._content['files_count'] = self.user.document_set.count()+1
        self.fetch_notes_in_table()
        self._content['tables'] = {'notes': self._content2}
        self.fetch_files_in_table()
        self._content['tables']['files'] = self._content2

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
            AdminUtils(user=self.request.user, app_user=self.user).log(action_type='delete_note', action=action)
            note.delete()
            self._message = 'Note deleted successfully'
        else:
            self._message = 'Comment cannot be deleted'
            self._status = 'info'
        self.fetch_notes_in_table()
        self._content = self._content2

    def add_note(self):
        note = Note(user=self.request.user, app_user=self.user, body=self.kwargs['note'], super=self.kwargs.get('super') or False)
        Timeline(user=self.request.user, app_user=self.user, name='collection record',
                 body=self.kwargs['note'], overdue_days=f'Overdue {self.overdue_days(self.user.loan_set.last().disbursed_at)} Days').save()
        action = f'Added note: ({note.body[:15]}...)'
        AdminUtils(user=self.request.user, app_user=self.user).log(action_type='add_note', action=action)
        note.save()
        self._message = 'Note added successfully!'
        self.fetch_notes_in_table()
        self._content = self._content2

    def modify_note(self):
        note = Note.objects.get(pk=self.kwargs['note_id'])
        if note.body != self.kwargs['note'] and not note.super:
            action = f'Modified note: ({note.body[:15]}...)'
            AdminUtils(user=self.request.user, app_user=self.user).log(action_type='add_note', action=action)
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
        self.add_table_content(_for='file', file=self.user.avatar)
        for file in self.user.document_set.all():
            self.add_table_content(_for='file', file=file)

    def update_user(self):
        key = self.kwargs['key']
        value = self.kwargs['value']
        if value == getattr(self.user, key):
            self._message = 'No changes was made'
            self._status = 'info'
            return None
        log_detail = f"Updated user's {key} from {getattr(self.user, key)} to {value}"
        setattr(self.user, key, value)
        self.user.save()
        AdminUtils(self.request.user, app_user=self.user).log(action_type='profile update', action=log_detail)
        self._message = f'{key} updated successfully'

    def get_timeline(self):
        timelines = Timeline.objects.filter(app_user=self.user).order_by('-created_at').all()
        self._content2 = ''
        for tl in timelines:
            self.add_table_content(_for='timeline', tl=tl)
        self._content = self._content2

    def process(self):
        if self.action == "get_all_users":
            self.fetch_users_in_table(
                rows=self.kwargs.get('rows', 10),
                start=self.kwargs.get('start'),
                end=self.kwargs.get('end')
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

    def add_table_content(self, _for='', **kwargs):
        if _for == 'all_users_table':
            self._content += f"""
                                <tr 
                                    data-user_id='{self.user.user_id}' 
                                    data-first_name='{self.user.first_name}' 
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
                                    data-status='{self.user.status}' 
                                    data-status_pill='<span class="badge rounded-pill text-bg-{'success' if self.user.status else 'danger'}">{'Active' if self.user.status else 'Suspended'}</span>' 
                                    data-style='grey' 
                                    data-last_access='{self.user.last_access}' class='user_rows' data-bs-toggle='modal' data-bs-target='#exampleLargeModal1'>

                                    <td>
                                		<div class='d-flex align-items-center'>
                                		<div class="user-presence user-{'online' if self.user.status else 'offline'}" data-user_id="{self.user.user_id}">
                                			<img src="{kwargs['avatar']}" width="40" height="40" alt="" class="rounded-circle"></div>
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
                                            <span style="float: left; width: 40%" class="px-2"> By: S{note.user.stage}-{self.format_agent_id(note.user.stage_id)}
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
            		<div class="col-md-10">
            			<input type="text" class="form-control" value="{file.description.upper()}: {file.file.name.rsplit('/')[-1]}" disabled style="width: 100%; border-right: none">
            		</div>
            		<div class="col-md-2 text-end d-grid">
            			<a href="{file.file.url}" target='_blank'><button class="btn btn-primary">View <i class="bx bx-right-top-arrow-circle"></i></button></a>
            		</div>
            	</div>
            """

        elif _for == 'timeline':
            tl: Timeline = kwargs['tl']
            detail = ''
            body = ''
            overdue = f'<span class="badge text-bg-danger">{tl.overdue_days}</span>'
            if tl.name == 'transfer':
                body = f'Allocated to {tl.user.stage}-{self.format_agent_id(tl.user.stage_id)}'
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
                            <span class="badge text-bg-primary">{tl.user.stage}-{self.format_agent_id(tl.user.stage_id)}</span>
                            {detail}
                        </div>
                        <div class="mt-1">{body}</div>
                    </div>
                </li>
            """

    @staticmethod
    def format_agent_id(num: int):
        if num < 10:
            return f'00{num}'
        else:
            return f'0{num}'

    @staticmethod
    def overdue_days(disbursed_at):
        due_date = disbursed_at + dt.timedelta(days=LOAN_DURATION)
        diff = timezone.now() - due_date
        return diff.days

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
    def __init__(self, user, **kwargs):
        self.user: AdminUser = user
        self.kwargs = kwargs

    def log(self, action_type='', action=''):
        AdminLog(user=self.user, app_user=self.kwargs['app_user'], action_type=action_type, action=action).save()


class LoanUtils:
    def __init__(self, request, **kwargs):
        self.user, self.users, self.user_id, self._content, self._content2, self.loan = None, None, None, None, None, None
        self.kwargs = kwargs
        self.action = self.kwargs['action']
        self.request = request
        self._status, self._message = 'success', 'success'

    @staticmethod
    def disburse_loan(loan: Loan, admin_user):
        # raise 'Disburse function is not yet set'
        loan.amount_disbursed = (60/100)*loan.principal_amount
        loan.disbursed_at = timezone.now()
        loan.save()
        Timeline(user=admin_user, app_user=loan.user, name='disbursement', body=f'Loan of &#x20A6;{loan.principal_amount} was requested. &#x20A6;{loan.amount_disbursed} was disbursed').save()
        return

    def fetch_loans(self, size="single", rows=10, start=f'{dt.date.today()-dt.timedelta(days=60):%Y-%m-%d}', end=f'{dt.date.today():%Y-%m-%d}'):
        if size != 'single':
            start_date = dt.datetime.strptime(start, '%Y-%m-%d')
            start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

            end_date = dt.datetime.strptime(end, '%Y-%m-%d')
            end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

            loans = Loan.objects.filter(created_at__gte=start_date, created_at__lte=end_date).order_by(
                '-created_at').all()

            self._content = ''
            sn = 0
            for loan in loans[:int(rows)]:
                disbursed = '-'
                if loan.disbursed_at is not None:
                    disbursed = f'{loan.disbursed_at:%b %d, %Y}'
                sn += 1
                self.add_table_content(_for='loans', disbursed=disbursed, single=False, loan=loan, sn=sn, size=size)
        else:
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            # IF SIZE IS SINGLE
            loans = self.user.loan_set.order_by('-created_at').all()
            self._content = ''
            sn = 0
            for loan in loans:
                disbursed = '-'
                if loan.disbursed_at is not None:
                    disbursed = f'{loan.disbursed_at:%b %d, %Y}'
                sn += 1
                self.add_table_content(_for='loans', disbursed=disbursed, single=True, loan=loan, sn=sn, size=size)

    def fetch_waives(self, rows=10, start=f'{dt.date.today() - dt.timedelta(days=60):%Y-%m-%d}',
                    end=f'{dt.date.today():%Y-%m-%d}'):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d')
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

            end_date = dt.datetime.strptime(end, '%Y-%m-%d')
            end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

            repayments = Repayment.objects.filter(created_at__gte=start_date, created_at__lte=end_date).order_by('-id').all()

            self._content = ''
            sn = 0
            for repay in repayments[:int(rows)]:
                sn += 1
                self.add_table_content(_for='repayments', single=False, repay=repay, sn=sn, size=size)
        else:
            self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
            # IF SIZE IS SINGLE
            repayments = self.user.repayment_set.order_by('-id').all()
            self._content = ''
            sn = 0
            for repay in repayments:
                sn += 1
                self.add_table_content(_for='repayments', single=True, repay=repay, sn=sn, size=size)

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
            if Collection.objects.filter(loan=loan).exists() and Collection.objects.get(loan=loan) in collector.collection_set.all():
                checked = 'checked'
            if collector.level == "team leader":
                avail = "disabled"
                count = f"All {collector.stage}"
                checked = 'checked'
            self._content += f"""
                        <tr class='agents_trs'>
                		    <td>{collector.stage}-{LoanUtils.format_agent_id(collector.stage_id)}</td>
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
                       stage=LoanUtils.get_stage(loan)).save()
            overdue_days = LoanUtils.get_overdue_days(loan.disbursed_at) if loan.disbursed_at else '-'
            Timeline(user=collector, app_user=loan.user, name='manual assign',
                     body=f'Allocated to {collector.stage}-{LoanUtils.format_agent_id(collector.stage_id)}',
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

    @staticmethod
    def repayment(loan: Loan, amount_paid):
        print(loan)
        """
        Run this method after receiving payload, validating transaction, checking if duplicate
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
        overdue_days = LoanUtils.get_overdue_days(loan.disbursed_at)
        Timeline(user=admin_user, app_user=loan.user, name='repayment', body=f'Repayment of #{amount_paid:,} was made', detail=loan.status, overdue_days=f'Overdue {overdue_days} Days' if overdue_days > 0 and overdue_days != -1 else 'Due Day').save()

        Repayment(user=loan.user, admin_user=admin_user, loan=loan, principal_amount=loan.principal_amount, amount_due=loan.amount_due, amount_paid_now=amount_paid, total_paid=loan.amount_paid, stage=LoanUtils.get_stage(loan)).save()

    def status_update(self, to):
        loan = Loan.objects.get(pk=self.kwargs['loan_id'])
        self.user = AppUser.objects.get(user_id=self.kwargs['user_id'])
        if to == "repaid":
            if loan.status in ['repaid', 'declined', 'pending']:
                self._message = 'Action could not be completed, refresh page and try again'
                self._status = 'error'
                return
            note = f'Super Admin ({self.request.user.first_name}) has waived loan with ID ({loan.loan_id})'
            UserUtils(self.request, action='add_note', user_id=self.user.user_id, note=note, super=True).process()
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
            # DISBURSE LOAN
            self.disburse_loan(loan=loan, admin_user=self.request.user)

        loan_static = LoanStatic(user=self.request.user, loan=loan, status=to)
        loan.status = to
        loan.repaid_at = timezone.now() if to == "repaid" else None
        AdminUtils(user=self.request.user, app_user=loan.user).log(action_type='loan status', action=f'{to.title()} a loan with ID {loan.loan_id}')
        loan_static.save()
        loan.save()
        self._message = f'Loan {to} successfully'
        self._status = 'success'
        self.fetch_loans(size=self.kwargs['size'])

    def trash_loan(self):
        loan = Loan.objects.get(pk=self.kwargs['loan_id'])
        loan.delete()
        AdminUtils(user=self.request.user, app_user=loan.user).log(action_type='loan status', action=f'Deleted a loan with ID {loan.loan_id}')
        self._message = f'Loan request deleted successfully'
        self._status = 'success'
        self.fetch_loans(size=self.kwargs['size'])

    def waive_loan(self):
        loan = Loan.objects.get(pk=self.kwargs.get('loan_id'))
        amount = self.kwargs.get('amount')
        loan_obj = None
        if self.request.user.level in ['super admin', 'approval admin']:
            if amount and loan:
                if float(amount) > loan.amount_due:
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
            elif float(amount) > loan.amount_due:
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
                attach_user = f"<td>{loan.user.user_id}</td>"
            else:
                attach_user = ''

            try:
                avatar = loan.user.avatar.file.url
            except:
                avatar = '/static/admin_panel/images/avatars/user.png'

            status_text, status_class = self.get_loan_status()

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}' 
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
                                    data-last_access='{loan.user.last_access}' class='loan_rows' data-bs-toggle='modal' data-bs-target='#exampleLargeModal1'
                                    data-loan_id='{loan.loan_id}'">
                            <td>{kwargs['sn']}.</td>
                            <td>{loan.loan_id}
                            <span class="badge bg-{'warning' if loan.reloan == 1 else 'info'}">{'1st loan' if loan.reloan == 1 else f'reloan ({loan.reloan})'}</span>
                            </td>
                            {attach_user}
                			<td>&#x20A6;{loan.principal_amount:,}</td>
                			<td>&#x20A6;{loan.amount_disbursed:,}</td>
                			<td>&#x20A6;{loan.amount_due:,}</td>
                			<td>&#x20A6;{loan.amount_paid:,} {'<span class="rounded-pill badge text-bg-dark">waive</span>' if loan.waive_set.exists() else ''}</td>
                			<td>{loan.created_at:%b %d, %Y}</td>
                			<td>{kwargs['disbursed']}</td>
                			<td>{self.get_due_date()}</td>
                			<td>{self.overdue_days()}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text.title()} {LoanUtils.get_stage(loan)}</div>
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
                                        <li data-id='{loan.id}' data-action='declined' class='loan_actions text-danger'><a class='dropdown-item'><i class='bx bx-x font-22 '></i> Decline</a></li>
                                        """
                    if loan.status == "approved":
                        self._content += f"""
                                        <li data-id='{loan.id}' data-user_id='{loan.user.user_id}' data-size='{kwargs["size"]}' data-action='disbursed' class='loan_actions text-primary'><a class='dropdown-item'><i class='bx bx-check font-22 '></i> Disburse</a></li>
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
            if not kwargs['single']:
                attach_user = f"<td>{loan.user.user_id}</td>"
            else:
                attach_user = ''

            try:
                avatar = loan.user.avatar.file.url
            except:
                avatar = '/static/admin_panel/images/avatars/user.png'

            status_text, status_class = self.get_loan_status()

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}' 
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
                            <td>{kwargs['sn']}.</td>
                            <td>{loan.loan_id}</td>
                            {attach_user}
                			<td>&#x20A6;{loan.principal_amount:,}</td>
                			<td>&#x20A6;{loan.amount_due:,}</td>
                			<td>&#x20A6;{repay.amount_paid_now:,}</td>
                			<td>{LoanUtils.get_stage(loan)}</td>
                			<td>&#x20A6;{repay.total_paid:,}</td>
                			<td>
                                <div class='badge rounded-pill w-100 text-bg-{status_class}'>{status_text.title()} </div>
                            </td>
                            <td>{repay.created_at:%b %d, %Y}</td>
                            </tr>
                		"""

        if _for == "waives":
            waive = kwargs['waive']
            self.loan, loan = waive.loan, waive.loan

            try:
                avatar = loan.user.avatar.file.url
            except:
                avatar = '/static/admin_panel/images/avatars/user.png'

            self._content += f"""
                        <tr data-user_id='{loan.user.user_id}' 
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
                			<td>{self.get_due_date()}</td>
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
                             end=self.kwargs.get('end')
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
            elif self.action == "fetch_assigned":
                self.fetch_assigned(Loan.objects.get(loan_id=self.kwargs['loan_id']))
            elif self.action == "assign":
                self.assign(
                    loan=Loan.objects.get(loan_id=self.kwargs['loan_id']),
                    action=self.kwargs.get('main_action'),
                    collector=AdminUser.objects.get(pk=self.kwargs.get('collector_id'))
                )

    def overdue_days(self):
        if self.loan.disbursed_at is not None:
            due_date = self.loan.disbursed_at + dt.timedelta(days=self.loan.duration)
            diff = timezone.now() - due_date
            if diff.days < -1:
                return '-' if self.loan.status != 'repaid' else f'repaid: {self.loan.repaid_at:%b %d}'
            return diff.days if self.loan.status != 'repaid' else f'repaid: {self.loan.repaid_at:%b %d}'
        return '-'

    def get_loan_status(self):
        status = ''
        if self.loan.disbursed_at is not None:
            due_date = self.loan.disbursed_at + dt.timedelta(days=self.loan.duration)
            diff = timezone.now() - due_date
            if diff.days == 0:
                status = 'due'
            elif diff.days > 0 and self.loan.amount_paid < self.loan.amount_due:
                status = 'overdue'
            else:
                status = self.loan.status
        else:
            status = self.loan.status

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

    def get_due_date(self):
        if self.loan.disbursed_at is not None:
            return f'{(self.loan.disbursed_at + dt.timedelta(days=self.loan.duration)):%b %d, %Y}'
        return '-'

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
    def format_agent_id(num: int):
        if num < 10:
            return f'00{num}'
        else:
            return f'0{num}'

    @staticmethod
    def get_overdue_days(disbursed_at):
        due_date = disbursed_at + dt.timedelta(days=LOAN_DURATION)
        diff = timezone.now() - due_date
        return diff.days

    @staticmethod
    def generate_dummy_loans(start_date, end_date=f'{dt.date.today():%Y-%m-%d}', count_per_day=random.randint(8, 20)):
        start_date = dt.datetime.strptime(start_date, '%Y-%m-%d').date()
        start_date = dt.datetime.combine(start_date, dt.time.min)
        end_date = dt.datetime.strptime(end_date, '%Y-%m-%d').date()
        end_date = dt.datetime.combine(end_date, dt.time.min)

        current_date = timezone.make_aware(start_date, timezone.get_current_timezone())
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())
        total_added = 0
        while current_date <= end_date:
            for no in range(count_per_day):
                loan_id = random.randint(1000, 10000)
                user = AppUser.objects.get(pk=1)
                principal_amount = math.ceil(random.randint(3000, 30000) / 1000) * 1000
                amount_disbursed = 0
                amount_due = principal_amount
                amount_paid = 0
                disbursed_at = None
                reloan = random.randint(1, 3)
                status = random.choice(['pending', 'approved', 'disbursed', 'disbursed'])
                if status == 'disbursed' or status == 'repaid':
                    amount_disbursed = (60/100)*principal_amount
                    disbursed_at = current_date
                    if status == 'repaid':
                        amount_paid = amount_due
                new_loan = Loan(user=user, principal_amount=principal_amount, amount_disbursed=amount_disbursed, amount_due=amount_due, amount_paid=amount_paid, disbursed_at=disbursed_at, reloan=reloan, status=status, created_at=current_date)
                new_loan.save()
                new_loan.loan_id = f'SL{new_loan.id}{random.randint(100, 1000)}'
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
                    random_perc = math.ceil(random.randint(5, 90)/4) * 4
                    amount_paid = (random_perc/100)*(loan.amount_due - loan.amount_paid)
                    statuses['part'] += 1
                else:
                    amount_paid = loan.amount_due - loan.amount_paid
                    statuses['repaid'] += 1
                LoanUtils.repayment(loan, amount_paid)
        print(statuses)

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

    @staticmethod
    def set_progressive():
        """
        Must be run at the end of each day
        :return:
        """
        loans = Loan.objects.filter(disbursed_at__gte=timezone.now()-dt.timedelta(days=37))
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
                    When((~Q(status='repaid') & Q(reloan=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan=1)), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            unpaid_count_reloan=Count(
                Case(
                    When((~Q(status='repaid') & Q(reloan__gt=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan__gt=1)), then='id'),
                    default=Value(None),
                    output_field=django.db.models.IntegerField()
                )
            ),
            unpaid_sum=Sum(
                Case(
                    When((~Q(status='repaid') & Q(reloan=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan=1)), then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            ),
            unpaid_sum_reloan=Sum(
                Case(
                    When((~Q(status='repaid') & Q(reloan__gt=1)) | (Q(amount_paid__lt=F('amount_due')) & Q(reloan__gt=1)),
                         then='amount_due'),
                    default=Value(0),
                    output_field=django.db.models.FloatField()
                )
            )
        ).values('day', 'total_count', 'total_sum', 'unpaid_sum', 'unpaid_count', 'total_count_reloan', 'total_sum_reloan', 'unpaid_sum_reloan', 'unpaid_count_reloan')

        # Progressive(disbursed_at=(timezone.now()-dt.timedelta(days=7)).date()).save()
        for day in range(-1, 32):
            for loan in daily_loans:
                if Analysis.is_in_progressive_category(loan['day'], day):
                    current_row, created = Progressive.objects.get_or_create(disbursed_at=timezone.make_aware(dt.datetime.combine(loan['day'].date(), dt.time.min), timezone.get_current_timezone()))
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

        end_date = dt.datetime.strptime(end, '%Y-%m-%d')
        end_date = timezone.make_aware(end_date, timezone.get_current_timezone())

        progressive = Progressive.objects.filter(disbursed_at__gte=start_date, disbursed_at__lte=end_date).order_by('-disbursed_at').all()
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
    def set_collectors():
        """
        To be run at the beginning of every day
        :return:
        """
        # First clear collections
        Analysis.clear_collections()

        # Start set collections
        exempt_loans = [int(col.loan.id) for col in Collection.objects.all()]
        if exempt_loans:
            loans = Loan.objects.filter(Q(disbursed_at__isnull=False) & Q(status='disbursed') & ~Q(pk__in=exempt_loans)).all()
        else:
            loans = Loan.objects.filter(Q(disbursed_at__isnull=False) & Q(status='disbursed')).all()
        stages = ['S-1', 'S0', 'S1', 'S2', 'S3', 'S4', 'M1']
        staged_loans = {}
        for stage in stages:
            staged_loans[stage] = []
            for loan in loans:
                if Analysis.is_in_category(loan.disbursed_at, stage):
                    staged_loans[stage].append(loan)

        # CHECK FOR ACTIVE COLLECTORS AND SHARE AVAILABLE LOANS WITH THEM
        count_per_stage = {stage: int(len(staged_loans[stage]) / (AdminUser.objects.filter(level='staff', stage=stage, can_collect=True).count())) for stage in stages}

        for stage, count in count_per_stage.items():
            loan_index = 0
            for collector in AdminUser.objects.filter(level='staff', stage=stage, can_collect=True).all():
                assigned_loans = staged_loans[stage][loan_index:loan_index + count]
                loan_index += count
                for loan in assigned_loans:
                    Collection(user=collector, loan=loan, amount_due=loan.amount_due, amount_paid=loan.amount_paid, stage=stage).save()
                    Timeline(user=collector, app_user=loan.user, name='transfer',
                             body=f'Allocated to {collector.stage}-{Analysis.format_agent_id(collector.stage_id)}',
                             overdue_days=f'Overdue {Analysis.overdue_days(loan.disbursed_at)} Days').save()

    def get_collections(self,
                        stage='S-1,S0',
                        start=f'{dt.date.today() - dt.timedelta(days=500):%Y-%m-%d}',
                        end=f'{dt.date.today():%Y-%m-%d}',
                        ):
        start_date = dt.datetime.strptime(start, '%Y-%m-%d')
        start_date = timezone.make_aware(start_date, timezone.get_current_timezone())

        end_date = dt.datetime.strptime(end, '%Y-%m-%d')
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
    def clear_collections():
        """
        Must be run before set_collectors
        :return: None
        """
        collections = Collection.objects.all()
        for col in collections:
            if col.stage in ['S-1', 'S0']:
                col.delete()
            else:
                # CLEAR COLLECTIONS AT THE LAST DAY OF EACH STAGE
                if col.stage == 'S1' and Analysis.overdue_days(col.loan.disbursed_at) == 3:
                    col.delete()
                elif col.stage == 'S2' and Analysis.overdue_days(col.loan.disbursed_at) == 7:
                    col.delete()
                elif col.stage == 'S3' and Analysis.overdue_days(col.loan.disbursed_at) == 15:
                    col.delete()
                elif col.stage == 'S4' and Analysis.overdue_days(col.loan.disbursed_at) == 30:
                    col.delete()

    def generate_chart(self, _for=''):
        if _for == 'real_day':
            self._content = ''
            for result in self._result:
                self.add_table_content(_for='real_day', result=result)

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
                    <th scope="row">{user.stage}-{self.format_agent_id(user.stage_id)}</th>
                    <td>{fields['ciq']:,}</td>
                    <td>{fields['new']:,}</td>
                    <td>&#x20A6; {fields['amount_held']:,}</td>
                    <td>{fields['paid_count']:,}</td>
                    <td>{fields['partpayment_count']:,}</td>
                    <td>{(fields['paid_count']/fields['ciq'])*100:.1f}%</td>
                    <td>&#x20A6;{fields['amount_paid']:,}</td>
                    <td>{(fields['amount_paid']/fields['amount_held'])*100:.1f}%</td>
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
    def overdue_days(disbursed_at):
        due_date = disbursed_at + dt.timedelta(days=LOAN_DURATION)
        diff = timezone.now() - due_date
        return diff.days

    @staticmethod
    def is_in_category(disbursed_at, cat):
        due_date = disbursed_at + dt.timedelta(days=LOAN_DURATION)
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

    @staticmethod
    def format_agent_id(num: int):
        if num < 10:
            return f'00{num}'
        else:
            return f'0{num}'

    @property
    def result(self):
        return self._result

    @property
    def content(self):
        return self._content




