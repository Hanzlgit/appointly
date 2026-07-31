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
        "locations/<int:location_id>/resources/",
        views.CatalogLocationResourceListCreateView.as_view(),
        name="catalog-location-resources",
    ),
    path(
        "locations/<int:location_id>/resources/<int:resource_id>/",
        views.CatalogLocationResourceRetrieveUpdateDestroyView.as_view(),
        name="catalog-location-resource-detail",
    ),
    path(
        "services/",
        views.CatalogServiceListCreateView.as_view(),
        name="catalog-services",
    ),
    path(
        "services/<int:service_id>/",
        views.CatalogServiceRetrieveUpdateDestroyView.as_view(),
        name="catalog-service-detail",
    ),
    path(
        "public/",
        views.CatalogPublicBrowseView.as_view(),
        name="catalog-public",
    ),
]
