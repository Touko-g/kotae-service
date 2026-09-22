import re
from datetime import datetime, timedelta
from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from articles.models import Article
from .models import User, VerifyCode, ResetCode
from chat.models import Online

EMAIL_REGEX = re.compile(r"^\S+@\S+\.\S+$")


class UserSerializer(serializers.ModelSerializer):
    article = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'about', 'avatar', 'email', 'article', 'create_time', 'update_time')

    def get_article(self, obj):
        return len(Article.objects.filter(user_id=obj.id))


class UserResetPswSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    email = serializers.CharField(write_only=True, required=True)
    password2 = serializers.CharField(write_only=True, required=True)
    code = serializers.CharField(required=True, allow_blank=False, min_length=6, max_length=6, help_text='验证码',
                                 error_messages={
                                     'blank': '请输入验证码',
                                     'required': '请输入验证码',
                                     'min_length': '验证码格式错误',
                                     'max_length': '验证码格式错误',
                                 }, write_only=True)

    class Meta:
        model = User
        fields = ('email', 'code', 'password', 'password2')

    # 对code字段单独验证(validate_+字段名)
    def validate_code(self, code):
        verify_records = ResetCode.objects.filter(email=self.initial_data['email']).order_by('-add_time')
        print(verify_records)
        if verify_records:
            last_record = verify_records[0]
            # 判断验证码是否过期
            if last_record.use:
                raise serializers.ValidationError('验证码失效')
            five_minutes_ago = datetime.now() - timedelta(hours=0, minutes=2, seconds=0)  # 获取2分钟之前的时间
            if last_record.add_time < five_minutes_ago:
                raise serializers.ValidationError('验证码过期')
            # 判断验证码是否正确
            if last_record.code != code:
                raise serializers.ValidationError('验证码错误')
            # 不用将code返回到数据库中，只是做验证
            # return code
        else:
            raise serializers.ValidationError('验证码不存在')
        return code

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    # def update(self, instance, validated_data):
    #     user = User.objects.filter(email=validated_data['email'])[0]
    #
    #     user.set_password(validated_data['password'])
    #     user.save()
    #
    #     code = validated_data['code']
    #     code_instance = ResetCode.objects.filter(code=code)[0]
    #     code_instance.use = True
    #     code_instance.save()
    #     return user


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    code = serializers.CharField(required=True, allow_blank=False, min_length=6, max_length=6, help_text='验证码',
                                 error_messages={
                                     'blank': '请输入验证码',
                                     'required': '请输入验证码',
                                     'min_length': '验证码格式错误',
                                     'max_length': '验证码格式错误',
                                 }, write_only=True)

    class Meta:
        model = User
        fields = ('username', 'about', 'email', 'code', 'password', 'password2')

    # 对code字段单独验证(validate_+字段名)
    def validate_code(self, code):
        verify_records = VerifyCode.objects.filter(email=self.initial_data['email']).order_by('-add_time')
        if verify_records:
            last_record = verify_records[0]
            # 判断验证码是否过期
            if last_record.use:
                raise serializers.ValidationError('验证码失效')
            five_minutes_ago = datetime.now() - timedelta(hours=0, minutes=2, seconds=0)  # 获取2分钟之前的时间
            if last_record.add_time < five_minutes_ago:
                raise serializers.ValidationError('验证码过期')
            # 判断验证码是否正确
            if last_record.code != code:
                raise serializers.ValidationError('验证码错误')
            # 不用将code返回到数据库中，只是做验证
            # return code
        else:
            raise serializers.ValidationError('验证码不存在')
        return code

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        print(attrs)
        return attrs

    def create(self, validated_data):
        user = User.objects.create(
            username=validated_data['username'],
            email=validated_data['email'],
            about=validated_data['about']
        )

        user.set_password(validated_data['password'])
        user.save()

        Online.objects.create(user=user)

        code = validated_data['code']
        code_instance = VerifyCode.objects.filter(code=code)[0]
        code_instance.use = True
        code_instance.save()
        return user


class UserChangePswSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    old_password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('old_password', 'password', 'password2')

    def validate(self, attrs):
        if attrs['old_password'] == attrs['password']:
            raise serializers.ValidationError("same password")
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError("Password fields didn't match.")

        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is not correct")
        return value

    def update(self, instance, validated_data):
        user = self.context['request'].user
        if user.pk != instance.pk:
            raise serializers.ValidationError("You dont have permission for this user.")
        instance.set_password(validated_data['password'])
        instance.save()
        return instance


class UserUpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'about', 'avatar', 'email')

    # def validate_email(self, value):
    #     user = self.context['request'].user
    #     if value and User.objects.exclude(pk=user.pk).filter(email=value).exists():
    #         raise serializers.ValidationError({"email": "This email is already in use."})
    #     return value
    #
    # def validate_username(self, value):
    #     user = self.context['request'].user
    #     if User.objects.exclude(pk=user.pk).filter(username=value).exists():
    #         raise serializers.ValidationError({"username": "This username is already in use."})
    #     return value

    def update(self, instance, validated_data):
        user = self.context['request'].user
        if user.pk != instance.pk:
            raise serializers.ValidationError({"authorize": "You dont have permission for this user."})

        instance.username = validated_data['username']
        instance.about = validated_data['about']
        instance.avatar = validated_data['avatar']
        instance.email = validated_data['email']

        instance.save()

        return instance


class VerifyCodeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, email):
        """
        验证邮箱是否合法
        """
        # 邮箱是否注册
        if User.objects.filter(email=email).count():
            raise serializers.ValidationError('该邮箱已经注册')

        # 验证邮箱号码合法
        if not re.match(EMAIL_REGEX, email):
            raise serializers.ValidationError('邮箱格式错误')

        # 验证码发送频率
        one_minute_age = datetime.now() - timedelta(hours=0, minutes=2, seconds=0)
        if VerifyCode.objects.filter(add_time__gt=one_minute_age, email=email).count():
            raise serializers.ValidationError('请两分钟后再次发送')
        return email


class ResetCodeSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, email):
        """
        验证邮箱是否合法
        """
        if not re.match(EMAIL_REGEX, email):
            raise serializers.ValidationError('邮箱格式错误')
        # 注意：不在此处校验「邮箱是否已注册」，避免被用来枚举账号；由视图统一处理

        # 验证码发送频率
        one_minute_age = datetime.now() - timedelta(hours=0, minutes=2, seconds=0)
        if ResetCode.objects.filter(add_time__gt=one_minute_age, email=email).count():
            raise serializers.ValidationError('请两分钟后再次发送')
        return email
