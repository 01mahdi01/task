from django.urls import path
from .apis import ProfileApi, RegisterApi, AddSignature


urlpatterns = [
    path('register/', RegisterApi.as_view(),name="register"),
    path('profile/', ProfileApi.as_view(),name="profile"),
    path('sign/', AddSignature.as_view(),name="add_signature"),

]
