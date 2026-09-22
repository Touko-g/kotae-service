from rest_framework.response import Response
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest
from django.db.utils import IntegrityError
from .serializers import ArticleSerializer, TagSerializer, LikeSerialize, CommentSerializer, SearchSerializer, \
    NoticeSerializer, PhotoSerializer
from .models import Article, Tag, Like, Comment, Search, Notice, Photo
from rest_framework import generics, permissions, status, viewsets, serializers, mixins
from rest_framework.views import APIView
from api.mixins import StaffEditorPermissionMixin, UserQuerySetMixin, PublicQuerySetMixin
from api.permissons import IsEditBySelfPermission
from .filters import ArticleFilter, TagFilter, LikeFilter, CommentFilter, SearchFilter, NoticeFilter, PhotoFilter
import requests
import json


def get_ip(request):
    ip = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if not ip:
        ip = request.META.get('REMOTE_ADDR', "")
    client_ip = ip.split(",")[-1].strip() if ip else ""
    return client_ip


def get_position(ip):
    if ip != '127.0.0.1':
        url = "http://opendata.baidu.com/api.php?query=" + ip + "&co=&resource_id=6006&oe=utf8"
        response = requests.get(url)
        return json.loads(response.text)['data'][0]['location']
    return '未知'


# class ArticleViewSet(StaffEditorPermissionMixin, UserQuerySetMixin, viewsets.ModelViewSet):
#     queryset = Article.objects.all()
#     serializer_class = ArticleSerializer

class ArticleList(PublicQuerySetMixin, generics.ListAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filterset_class = ArticleFilter


class ArticleCreate(generics.CreateAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        tags = self.request.data['tag']
        serializer.save(user=self.request.user)
        for tag in tags:
            instance = Tag.objects.get(name=tag["name"])
            instance.hot += 1
            instance.save()


class ArticleSingle(PublicQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    queryset = Article.objects.all()
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEditBySelfPermission]

    def get(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        if request.user:
            instance.views += 1
            instance.save()
        return Response(serializer.data)

    def perform_update(self, serializer):
        tags = self.request.data['tag']
        serializer.save(user=self.request.user)
        for tag in tags:
            instance = Tag.objects.get(name=tag["name"])
            instance.hot += 1
            instance.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user == instance.user or request.user.is_superuser:
            if instance.public:
                instance.public = False
                instance.save()
                return Response(status=status.HTTP_200_OK, data="OK")
            return Response(status=status.HTTP_400_BAD_REQUEST, data="文章不存在")
        return Response(status=status.HTTP_403_FORBIDDEN, data="没有权限")


class TagViewSet(PublicQuerySetMixin, viewsets.ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filterset_class = TagFilter

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if request.user.is_superuser:
            if instance.public:
                instance.public = False
                instance.save()
                return Response(status=status.HTTP_200_OK, data="OK")
            return Response(status=status.HTTP_400_BAD_REQUEST, data="标签已隐藏")
        return Response(status=status.HTTP_403_FORBIDDEN, data="没有权限")


class LikeViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    queryset = Like.objects.all()
    serializer_class = LikeSerialize
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEditBySelfPermission]
    filterset_class = LikeFilter

    def get_queryset(self, *args, **kwargs):
        # 细粒度可见性：管理员全量；带 article 参数时返回该文章的点赞人列表；
        # 否则只返回本人点赞，禁止无参全表拉取
        qs = super().get_queryset(*args, **kwargs)
        user = self.request.user
        if user.is_superuser:
            return qs
        article_id = self.request.query_params.get('article')
        if article_id:
            return qs.filter(article_id=article_id)
        return qs.filter(user=user)

    def perform_create(self, serializer):
        article = serializer.validated_data['article']
        try:
            with transaction.atomic():
                serializer.save(user=self.request.user)
                # 原子更新计数，避免并发下 likes 与真实点赞数漂移
                Article.objects.filter(pk=article.pk).update(likes=F('likes') + 1)
        except IntegrityError:
            # 并发重复点赞被数据库唯一约束拦截
            raise serializers.ValidationError('一次就够了')

    def perform_destroy(self, instance):
        with transaction.atomic():
            instance.delete()
            # Greatest 防止计数减为负数
            Article.objects.filter(pk=instance.article_id).update(
                likes=Greatest(F('likes') - 1, 0))


class CommentViewSet(PublicQuerySetMixin, viewsets.ModelViewSet):
    queryset = Comment.objects.all()
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEditBySelfPermission]
    filterset_class = CommentFilter

    def get_queryset(self):
        return super().get_queryset().filter(reply=None)

    def perform_create(self, serializer):
        request = self.request
        serializer.save(user=request.user, ip_address=get_position(get_ip(request)))
        article = serializer.validated_data['article']
        content = serializer.validated_data['content']
        if serializer.data.get('reply') is not None:
            parent = Comment.objects.filter(id=serializer.data.get('reply'))[0]
            Notice.objects.create(user=request.user, recipient=parent.user, verb='回复', target=article,
                                  content=content, reply_content=parent.content)
        if request.user != article.user and serializer.data.get('reply') is None:
            Notice.objects.create(user=request.user, recipient=article.user, verb='评论', target=article,
                                  content=content)
        article.comments += 1
        article.save()

    def perform_destroy(self, instance):
        article = instance.article
        article.comments -= 1
        article.save()
        instance.public = False
        instance.save()
        # instance.delete()


class SearchViewSet(PublicQuerySetMixin, viewsets.ModelViewSet):
    queryset = Search.objects.all()
    serializer_class = SearchSerializer
    permission_classes = [permissions.AllowAny]
    filterset_class = SearchFilter

    def perform_create(self, serializer):
        request = self.request
        if Search.objects.filter(name=request.data['name']).exists():
            instance = Search.objects.filter(name=request.data['name'])[0]
            instance.hot += 1
            instance.save()
        else:
            serializer.save()

    def perform_update(self, serializer):
        raise serializers.ValidationError('不允许修改')

    def perform_destroy(self, instance):
        raise serializers.ValidationError('不允许删除')


class NoticeList(PublicQuerySetMixin, generics.ListAPIView):
    queryset = Notice.objects.all()
    serializer_class = NoticeSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = NoticeFilter

    def get_queryset(self, *args, **kwargs):
        # if self.request.user.is_superuser:
        #     return super().get_queryset()
        return super().get_queryset().filter(recipient=self.request.user)


class NoticeRead(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.data.get('id') is not None:
            results = Notice.objects.filter(id=request.data.get('id'))
            if len(results) > 0:
                instance = results[0]
                if request.user.id == instance.recipient.id:
                    instance.read = True
                    instance.save()
                    return Response('已读', status=200)
                return Response('没有权限', status=401)
        results = Notice.objects.filter(recipient=self.request.user, read=False)
        if len(results) > 0:
            for i in results:
                i.read = True
                i.save()
            return Response('已读')
        return Response('没有未读的信息')


class PhotoViewSet(PublicQuerySetMixin, viewsets.ModelViewSet):
    queryset = Photo.objects.all()
    serializer_class = PhotoSerializer
    permission_classes = [permissions.IsAuthenticated, IsEditBySelfPermission]
    filterset_class = PhotoFilter

    def perform_create(self, serializer):
        request = self.request
        serializer.save(user=request.user)
