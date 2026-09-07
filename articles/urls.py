from rest_framework import routers
from .views import ArticleList, ArticleSingle, ArticleCreate, TagViewSet, LikeViewSet, CommentViewSet, SearchViewSet, \
    NoticeList, NoticeRead, PhotoViewSet
from django.urls import path

urlpatterns = [
    path('article/', ArticleList.as_view()),
    path('article/create/', ArticleCreate.as_view()),
    path('article/<int:pk>/', ArticleSingle.as_view()),
    path('notice/', NoticeList.as_view()),
    path('notice_read/', NoticeRead.as_view())
]

router = routers.DefaultRouter()
router.register(r'tag', TagViewSet, basename='tag')
router.register(r'like', LikeViewSet, basename='like')
router.register(r'comment', CommentViewSet, basename='comment')
router.register(r'search', SearchViewSet, basename='search')
router.register(r'photo', PhotoViewSet, basename='photo')
urlpatterns += router.urls
