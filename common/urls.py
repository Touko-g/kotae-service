from rest_framework import routers
from django.urls import re_path, path
from . import views

urlpatterns = [
    path('user/resetpsw/', views.UserRestPswViewSet.as_view()),
    path('user/editpsw/<int:pk>/', views.ChangePasswordView.as_view()),
    path('user/<int:pk>/', views.UpdateProfileView.as_view()),
    path('code/', views.VerifyCodeViewSet.as_view()),
    path('resetcode/', views.ResetCodeViewSet.as_view()),
    path('register/', views.RegisterView.as_view()),
    path('logout/', views.LogoutView.as_view()),
    path('logout_all/', views.LogoutAllView.as_view())
]

router = routers.DefaultRouter()
router.register(r'users', views.UserViewSet, basename='users')
urlpatterns += router.urls
