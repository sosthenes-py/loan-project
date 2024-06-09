from django.contrib import admin
from .models import User, AdminLog, Note, LoanStatic, Repayment, Progressive, Collection, Waive, Timeline

# Register your models here.
admin.site.register(User)
admin.site.register(AdminLog)
admin.site.register(Note)
admin.site.register(LoanStatic)
admin.site.register(Repayment)
admin.site.register(Progressive)
admin.site.register(Collection)
admin.site.register(Waive)
admin.site.register(Timeline)

