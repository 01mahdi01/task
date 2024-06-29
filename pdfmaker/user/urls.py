from django.urls import path
from .apis import ProfileApi, RegisterApi, AddSignature, LoginView, StartPdfTaskView, CheckTaskStatusView

urlpatterns = [
    path('register/', RegisterApi.as_view(), name="register"),
    path('profile/', ProfileApi.as_view(), name="profile"),
    path('login/', LoginView.as_view(), name="login"),
    path('sign/', AddSignature.as_view(), name="add_signature"),
    path('start_pdf_task/', StartPdfTaskView.as_view(), name='start_pdf_task'),
    path('check_task_status/', CheckTaskStatusView.as_view(), name='check_task_status'),
]
