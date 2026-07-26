from django.contrib import admin

from scheduling.models import Booking, ScheduleRule, TimeSlot

admin.site.register(ScheduleRule)
admin.site.register(TimeSlot)
admin.site.register(Booking)
