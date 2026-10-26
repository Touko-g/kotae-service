from django.http import StreamingHttpResponse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import AiCredentialWriteSerializer, serialize_credential
from .throttling import AiRateThrottle


def _error_response(exc):
    return Response(
        {'detail': exc.detail, 'code': exc.code},
        status=exc.status,
    )


class AiBaseView(APIView):
    """所有 AI 接口的公共前提：必须登录。

    AI 能力按用户各自的 key 计费，匿名调用没有任何意义，
    所以这里统一收紧到 IsAuthenticated（而不是全站的 IsAuthenticatedOrReadOnly）。
    """

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [AiRateThrottle]


class AiCredentialView(AiBaseView):
    """GET/PUT/DELETE /api/ai/credential/

    GET    查询是否已配置（只返回掩码，不回明文）
    PUT    保存或更新（api_key 留空表示沿用旧 key）
    DELETE 清除
    """

    def get(self, request):
        credential = services.get_credential(request.user, required=False)
        return Response(serialize_credential(credential))

    def put(self, request):
        serializer = AiCredentialWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            credential, created = serializer.save(request.user)
        except Exception as exc:  # 加密/写库失败都按服务端错误处理
            return _error_response(services.AiServiceError(
                f'保存失败：{exc}', 500, 'ai_internal_error'))

        return Response(
            serialize_credential(credential),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request):
        from .models import AiCredential

        deleted, _ = AiCredential.objects.filter(user=request.user).delete()
        return Response({'deleted': bool(deleted)})


class AiChatView(AiBaseView):
    """POST /api/ai/chat/ —— 非流式对话。"""

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            credential = services.get_credential(request.user)
            messages = services.normalize_messages(body.get('messages'))
            result = services.request_chat(credential, messages, body)
        except services.AiServiceError as exc:
            return _error_response(exc)
        return Response(result)


class AiChatStreamView(AiBaseView):
    """POST /api/ai/chat-stream/ —— SSE 流式对话。

    每个 data 是一行归一化事件：
      {"type":"delta","content":"..."}
      {"type":"done","model":"...","usage":{...},"finishReason":"stop"}
      {"type":"error","message":"..."}
    """

    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        try:
            credential = services.get_credential(request.user)
            messages = services.normalize_messages(body.get('messages'))
            # 连通性在这里校验：失败时还没写 SSE 头，可以正常返回 JSON 错误
            upstream = services.open_stream(credential, messages, body)
        except services.AiServiceError as exc:
            return _error_response(exc)

        model = body.get('model') or credential.default_model or services.default_model()

        response = StreamingHttpResponse(
            services.iter_stream(upstream, request.user, model),
            content_type='text/event-stream; charset=utf-8',
        )
        response['Cache-Control'] = 'no-cache, no-transform'
        response['Connection'] = 'keep-alive'
        # 反代（nginx / 云托管）不缓冲，否则前端拿不到逐字输出
        response['X-Accel-Buffering'] = 'no'
        return response


class AiModelsView(AiBaseView):
    """GET /api/ai/models/ —— 可选模型（拿不到上游就用内置清单）。"""

    def get(self, request):
        try:
            credential = services.get_credential(request.user)
            return Response(services.fetch_models(credential))
        except services.AiServiceError as exc:
            return _error_response(exc)


class AiQuotaView(AiBaseView):
    """GET /api/ai/quota/ —— 当前用户自己的用量。"""

    def get(self, request):
        return Response(services.read_quota(request.user))
