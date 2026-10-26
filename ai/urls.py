from django.urls import path

from . import views

urlpatterns = [
    path('ai/credential/', views.AiCredentialView.as_view(), name='ai-credential'),
    path('ai/chat/', views.AiChatView.as_view(), name='ai-chat'),
    path('ai/chat-stream/', views.AiChatStreamView.as_view(), name='ai-chat-stream'),
    path('ai/models/', views.AiModelsView.as_view(), name='ai-models'),
    path('ai/quota/', views.AiQuotaView.as_view(), name='ai-quota'),
]
