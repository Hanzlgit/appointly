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
        "locations/<int:location_id>/services/",
        views.CatalogLocationServiceListCreateView.as_view(),
        name="catalog-location-services",
    ),
    path(
        "locations/<int:location_id>/services/<int:service_id>/",
        views.CatalogLocationServiceRetrieveUpdateDestroyView.as_view(),
        name="catalog-location-service-detail",
    ),
    path(
        "public/",
        views.CatalogPublicBrowseView.as_view(),
        name="catalog-public",
    ),
]
