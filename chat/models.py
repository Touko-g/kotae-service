from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL  # auth.User


# Create your models here.
class AbstractBaseModel(models.Model):
    create_time = models.DateTimeField('创建时间', null=True, blank=True, auto_now_add=True)
    update_time = models.DateTimeField('更新时间', null=True, blank=True, auto_now=True)
    public = models.BooleanField(default=True)

    class Meta:
        abstract = True


class Online(AbstractBaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    online = models.BooleanField(default=False, editable=False)


class Chat(AbstractBaseModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.CharField('信息', max_length=1000)
