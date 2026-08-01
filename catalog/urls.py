from django.urls import path

from catalog import views

urlpatterns = [
    path(
        "locations/",
        views.CatalogLocationListCreateView.as_view(),
        name="catalog-locations",
    ),
    path(
        "locations/<int:location_id>/",
        views.CatalogLocationRetrieveUpdateDestroyView.as_view(),
        name="catalog-location-detail",
    ),
    path(
        "locations/<int:location_id>/stylists/",
        views.CatalogLocationStylistListCreateView.as_view(),
        name="catalog-location-stylists",
    ),
    path(
        "locations/<int:location_id>/stylists/<int:stylist_id>/",
        views.CatalogLocationStylistRetrieveUpdateDestroyView.as_view(),
        name="catalog-location-stylist-detail",
    ),
    path(
        "stylists/<int:stylist_id>/services/",
        views.CatalogStylistServiceListCreateView.as_view(),
        name="catalog-stylist-services",
    ),
    path(
        "stylists/<int:stylist_id>/services/<int:service_id>/",
        views.CatalogStylistServiceRetrieveUpdateDestroyView.as_view(),
        name="catalog-stylist-service-detail",
    ),
]
