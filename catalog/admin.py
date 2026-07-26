from django.contrib import admin

from catalog.models import CatalogBusinessReference, Location, Resource, Service

admin.site.register(Location)
admin.site.register(Service)
admin.site.register(Resource)
admin.site.register(CatalogBusinessReference)
