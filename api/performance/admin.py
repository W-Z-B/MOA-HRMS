from django.contrib import admin

from performance.models import Appraisal, AppraisalCycle, Goal

admin.site.register(AppraisalCycle)
admin.site.register(Appraisal)
admin.site.register(Goal)
