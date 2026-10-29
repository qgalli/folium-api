from django.urls import path
from . import importer_views

urlpatterns = [
    path('preview/', importer_views.CatalogImporterPreviewView.as_view(), name='importer-preview'),
    path('simulate/', importer_views.CatalogImporterSimulateView.as_view(), name='importer-simulate'),
    path('execute/', importer_views.CatalogImporterExecuteView.as_view(), name='importer-execute'),
    path('fetch-covers/', importer_views.CatalogImporterFetchCoversView.as_view(), name='importer-fetch-covers'),
]
