from django.contrib import admin
import loan_app.models as loan_app_models

# Register your models here.
admin.site.register(loan_app_models.AppUser)
admin.site.register(loan_app_models.Document)
admin.site.register(loan_app_models.Avatar)
admin.site.register(loan_app_models.DisbursementAccount)
admin.site.register(loan_app_models.Loan)
admin.site.register(loan_app_models.VirtualAccount),
admin.site.register(loan_app_models.SmsLog)
admin.site.register(loan_app_models.Contact)

