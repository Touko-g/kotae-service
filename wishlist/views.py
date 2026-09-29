from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from api.mixins import PublicQuerySetMixin
from api.permissons import IsEditBySelfPermission
from .filters import WishFilter
from .models import Wish
from .serializers import WishSerializer


class WishViewSet(PublicQuerySetMixin, viewsets.ModelViewSet):
    queryset = Wish.objects.all()
    serializer_class = WishSerializer
    # 公开可见：任何人（含未登录）可读；写入需登录；修改/删除仅本人或超管
    permission_classes = [permissions.IsAuthenticatedOrReadOnly, IsEditBySelfPermission]
    filterset_class = WishFilter

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        # 完成状态变化时同步维护完成时间
        completed = serializer.validated_data.get('completed')
        if completed is True:
            serializer.save(complete_time=timezone.now())
        elif completed is False:
            serializer.save(complete_time=None)
        else:
            serializer.save()

    def destroy(self, request, *args, **kwargs):
        # 心愿无审计价值，采用硬删除：删除后任何人（含超管）不再返回
        instance = self.get_object()
        instance.delete()
        return Response(status=status.HTTP_200_OK, data="OK")
