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


class Tag(AbstractBaseModel):
    name = models.CharField('tag', max_length=30)
    hot = models.PositiveIntegerField('热度', default=0, editable=False)


class Article(AbstractBaseModel):
    title = models.CharField('标题', max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tag = models.ManyToManyField(Tag, related_name='article_tag')
    views = models.PositiveIntegerField('浏览量', default=0, editable=False)
    content = models.TextField('内容', blank=True, null=True)
    likes = models.PositiveIntegerField('点赞量', default=0, editable=False)
    comments = models.PositiveIntegerField('评论数量', default=0, editable=False)


class Like(AbstractBaseModel):
    article = models.ForeignKey(Article, on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)

    class Meta:
        # 同一用户对同一文章只能点赞一次，数据库层兜底并发重复写入
        unique_together = ('user', 'article')


class Comment(AbstractBaseModel):
    article = models.ForeignKey(Article, on_delete=models.DO_NOTHING)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    reply = models.ForeignKey('self', on_delete=models.CASCADE, related_name='comment_reply', null=True, blank=True)
    content = models.TextField('评论', max_length=10000, null=False, blank=False)
    ip_address = models.TextField('ip地址', default='未知', editable=False)


class Search(AbstractBaseModel):
    name = models.CharField('查询内容', max_length=50)
    hot = models.PositiveIntegerField('热度', default=1, editable=False)


class Notice(AbstractBaseModel):
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
    recipient = models.ForeignKey(User, related_name='recipient', on_delete=models.DO_NOTHING)
    verb = models.CharField('行为', max_length=20)
    target = models.ForeignKey(Article, on_delete=models.DO_NOTHING)
    content = models.TextField('内容', max_length=10000, null=False, blank=False)
    reply_content = models.TextField('回复内容', max_length=10000, null=False, blank=False)
    read = models.BooleanField(default=False)


class Photo(AbstractBaseModel):
    name = models.CharField('图片名称', max_length=100, null=True, blank=True)
    picture = models.CharField('图片', max_length=2000)
    user = models.ForeignKey(User, on_delete=models.DO_NOTHING)
