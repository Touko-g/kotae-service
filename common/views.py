from random import choice

from rest_framework import viewsets, permissions, generics, status, mixins
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from api.mixins import PublicQuerySetMixin
from api.permissons import IsEditBySelfPermission
from . import serializers
from . import models
from .filters import UserFilter
from api.utlis import send_email_mes, get_random_code


# Create your views here.

class UserViewSet(viewsets.ModelViewSet):
    queryset = models.User.objects.all()
    serializer_class = serializers.UserSerializer
    permission_classes = [permissions.IsAdminUser]
    filterset_class = UserFilter


class RegisterView(generics.CreateAPIView):
    queryset = models.User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.RegisterSerializer


class UserRestPswViewSet(GenericAPIView):
    queryset = models.User.objects.all()
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.UserResetPswSerializer

    def put(self, request, *args, **kwargs):
        serializer = serializers.UserResetPswSerializer(data=request.data)
        if serializer.is_valid(raise_exception=True):
            email = request.data.get('email')
            password = request.data.get('password')
            code = request.data.get('code')

            users = models.User.objects.filter(email=email)
            user: models.User = users[0] if users else None
            user.set_password(password)
            user.save()

            codes = models.ResetCode.objects.filter(code=code)
            code: models.ResetCode = codes[0] if codes else None
            print('=========', code, '=========')
            code.use = True
            code.save()
            return Response('密码已重置')
        return Response('密码重置失败')


class ChangePasswordView(generics.UpdateAPIView):
    queryset = models.User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.UserChangePswSerializer


class UpdateProfileView(generics.UpdateAPIView, generics.RetrieveAPIView):
    queryset = models.User.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.UserUpdateProfileSerializer

    def get(self, request, *args, **kwargs):
        # if request.user.id != kwargs.get('pk'):
        #     return Response('没有权限', status=401)
        user = self.get_object()
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "about": user.about,
            "avatar": user.avatar
        }, status=200)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)


class LogoutAllView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        tokens = OutstandingToken.objects.filter(user_id=request.user.id)
        for token in tokens:
            t, _ = BlacklistedToken.objects.get_or_create(token=token)

        return Response(status=status.HTTP_205_RESET_CONTENT)


class VerifyCodeViewSet(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.VerifyCodeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 这一步相当于发送前验证
        # 从 validated_data 中获取 mobile
        email = serializer.validated_data["email"]
        # 随机生成code
        code = get_random_code(6)

        try:
            send_email_mes(f"注册验证码", email, code)
            code_record = models.VerifyCode(code=code, email=email)
            code_record.save()
            return Response({
                'detail': 'Verification code has been sent'
            }, status=200)
        except Exception as e:
            print('错误', e)
            return Response({
                'detail': 'Email sending failed'
            }, status=400)


class ResetCodeViewSet(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = serializers.ResetCodeSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)  # 这一步相当于发送前验证
        # 从 validated_data 中获取 mobile
        email = serializer.validated_data["email"]
        # 随机生成code
        code = get_random_code(6)

        try:
            send_email_mes(f"重置密码验证码", email, code)
            code_record = models.ResetCode(code=code, email=email)
            code_record.save()
            return Response({
                'detail': 'Verification code has been sent'
            }, status=200)
        except Exception as e:
            print('错误', e)
            return Response({
                'detail': 'Email sending failed'
            }, status=400)
