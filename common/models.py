from django.db import models
from django.contrib.auth.models import AbstractUser


# Create your models here.

class AbstractBaseModel(models.Model):
    create_time = models.DateTimeField('创建时间', null=True, blank=True, auto_now_add=True)
    update_time = models.DateTimeField('更新时间', null=True, blank=True, auto_now=True)
    public = models.BooleanField(default=True)

    class Meta:
        abstract = True


class User(AbstractUser, AbstractBaseModel):
    about = models.TextField('个人简介', max_length=100, null=True, blank=True, default='...')
    avatar = models.CharField('头像url', max_length=2000, blank=True, null=True,
                              default='https://chen-1302611521.cos.ap-nanjing.myqcloud.com/blog/avatar.png')
    email = models.EmailField('email address', unique=True)

    class Meta(AbstractUser.Meta):
        swappable = 'AUTH_USER_MODEL'


class VerifyCode(models.Model):
    email = models.EmailField(verbose_name="email", blank=True)
    code = models.CharField(max_length=8, verbose_name="验证码")
    use = models.BooleanField(default=False)
    add_time = models.DateTimeField(verbose_name='生成时间', auto_now_add=True)


class ResetCode(models.Model):
    email = models.EmailField(verbose_name="email", blank=True)
    code = models.CharField(max_length=8, verbose_name="验证码")
    use = models.BooleanField(default=False)
    add_time = models.DateTimeField(verbose_name='生成时间', auto_now_add=True)