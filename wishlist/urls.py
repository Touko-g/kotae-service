from rest_framework import routers

from .views import WishViewSet

router = routers.DefaultRouter()
router.register(r'wish', WishViewSet, basename='wish')

urlpatterns = router.urls
