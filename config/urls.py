from django.urls import include, path

urlpatterns = [
    path("", include("alumni.urls")),
]
