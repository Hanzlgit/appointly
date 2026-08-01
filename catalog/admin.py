from django.contrib import admin

from catalog.models import CatalogBusinessReference, Location, Service, Stylist

admin.site.register(Location)
admin.site.register(Stylist)
admin.site.register(Service)
admin.site.register(CatalogBusinessReference)
