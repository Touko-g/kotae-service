from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class AiCredential(models.Model):
    """用户自己的上游 API Key。

    一个用户一条记录；key 以密文形式保存，只在服务端解密后用于调用上游，
    任何接口都不会把它明文返回给前端。
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='ai_credential')
    api_key = models.TextField('API Key（密文）')
    base_url = models.CharField(
        '接口地址', max_length=500,
        default='https://dashscope.aliyuncs.com/compatible-mode/v1')
    default_model = models.CharField('默认模型', max_length=100, default='qwen3.8-flash')
    enabled = models.BooleanField('启用', default=True)
    create_time = models.DateTimeField('创建时间', auto_now_add=True)
    update_time = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = 'AI 凭据'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.user.username} 的 AI 凭据'


class AiUsage(models.Model):
    """按「用户 + 日期 + 模型」累计的 token 用量。

    每用户各自用自己的 key，所以账必须按用户分开记；
    官方额度只能去控制台看，这里记的是本站实际发起的调用。
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='ai_usage')
    date = models.DateField('日期')
    model = models.CharField('模型', max_length=100)
    requests = models.PositiveIntegerField('调用次数', default=0)
    prompt_tokens = models.PositiveIntegerField('输入 tokens', default=0)
    completion_tokens = models.PositiveIntegerField('输出 tokens', default=0)
    total_tokens = models.PositiveIntegerField('合计 tokens', default=0)

    class Meta:
        verbose_name = 'AI 用量'
        verbose_name_plural = verbose_name
        # 同一天同一模型只有一行，累加靠 F 表达式原子更新
        unique_together = ('user', 'date', 'model')
        ordering = ['-date', '-model']
        indexes = [models.Index(fields=['user', 'date'])]

    def __str__(self):
        return f'{self.user.username} {self.date} {self.model}'
