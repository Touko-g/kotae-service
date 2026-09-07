from django_filters import rest_framework as filters
from .models import Article, Tag, Like, Comment, Search, Notice, Photo


class ArticleFilter(filters.FilterSet):
    title = filters.CharFilter(lookup_expr='icontains')
    content = filters.CharFilter(lookup_expr='icontains')
    tag = filters.CharFilter(field_name='tag__name', lookup_expr='exact')
    author = filters.CharFilter(field_name='user__username', lookup_expr='exact')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
        ('views', 'views'),
        ('comments', 'comments'),
        ('likes', 'likes')
    ), )

    class Meta:
        model = Article
        fields = []


class TagFilter(filters.FilterSet):
    name = filters.CharFilter(lookup_expr='icontains')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('hot', 'hot'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
    ), )

    class Meta:
        model = Tag
        fields = []


class LikeFilter(filters.FilterSet):
    article = filters.NumberFilter(field_name='article')
    user = filters.CharFilter(field_name='user__username')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
    ), )

    class Meta:
        model = Like
        fields = []


class CommentFilter(filters.FilterSet):
    article = filters.NumberFilter(field_name='article')
    user = filters.CharFilter(field_name='user__username')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
    ), )

    class Meta:
        model = Comment
        fields = []


class SearchFilter(filters.FilterSet):
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
        ('hot', 'hot')
    ))

    class Meta:
        model = Search
        fields = []


class NoticeFilter(filters.FilterSet):
    read = filters.BooleanFilter(field_name='read')
    verb = filters.CharFilter(field_name='verb')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
    ))

    class Meta:
        model = Notice
        fields = []


class PhotoFilter(filters.FilterSet):
    user = filters.CharFilter(field_name='user__username')
    order = filters.OrderingFilter(fields=(
        ('id', 'id'),
        ('create_time', 'create_time'),
        ('update_time', 'update_time'),
    ), )

    class Meta:
        model = Photo
        fields = []
