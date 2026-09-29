from django.db import models
from django.conf import settings

from articles.models import AbstractBaseModel

User = settings.AUTH_USER_MODEL  # common.User


class Wish(AbstractBaseModel):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING, related_name='wish')
    title = models.CharField('想做的事', max_length=100)
    content = models.TextField('备注', max_length=10000, null=True, blank=True)
    completed = models.BooleanField('已完成', default=False)
    complete_time = models.DateTimeField('完成时间', null=True, blank=True)

    class Meta:
        # 固定排序，避免分页时结果不一致
        ordering = ['-id']
