"""SSE 流式对话的原生 ASGI 实现。

为什么不直接用 DRF 的 StreamingHttpResponse？
--------------------------------------------
Django 4.0 的 `ASGIHandler.send_response` 是这么写的：

    if response.streaming:
        for part in response:      # 同步迭代，跑在事件循环线程里
            await send(...)

也就是说，只要迭代器里有阻塞调用（`requests` 读上游分片就是），
整个 Daphne 事件循环会被按住，期间的 HTTP 请求和 WebSocket 消息全部停摆。
本项目还跑着 Channels 群聊，AI 生成 30 秒就把聊天冻 30 秒，不能接受。

这里改用一条独立的最小 ASGI 通道：
- 鉴权 / 限流 / 请求体解析在 Django 侧完成后才进流；
- 上游读取放在工作线程，通过 asyncio.Queue 回传，事件循环始终不阻塞；
- 客户端断开时置位停止标记，尽快关闭上游连接，避免继续计费。

其余四个接口（credential / chat / models / quota）都是普通请求，
继续走 DRF，没必要在这里重复实现。

WSGI 部署（`backend.wsgi`）下不会经过本模块，由 `views.AiChatStreamView` 兜底，
那条路径是同步迭代，在 WSGI 的线程模型里本来就是对的。
"""
import asyncio
import json
import threading

from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from . import services
from .throttling import AiRateThrottle

STREAM_PATH = '/api/ai/chat-stream'


class AiHttpRouter:
    """把流式对话从 Django 的 ASGI 处理器里摘出来，其余请求原样交给 Django。"""

    def __init__(self, fallback):
        self.fallback = fallback

    async def __call__(self, scope, receive, send):
        if (
            scope.get('type') == 'http'
            and scope.get('method') == 'POST'
            and scope.get('path', '').rstrip('/') == STREAM_PATH
        ):
            await handle_stream(scope, receive, send)
            return
        # OPTIONS 预检仍然交给 Django：corsheaders 中间件会正常应答
        await self.fallback(scope, receive, send)


# ---------------------------------------------------------------------------
# 请求解析
# ---------------------------------------------------------------------------

async def _read_body(receive):
    body = b''
    while True:
        message = await receive()
        if message['type'] == 'http.disconnect':
            return None
        body += message.get('body', b'')
        if not message.get('more_body', False):
            return body


def _header(scope, name):
    name = name.lower().encode('latin1')
    for key, value in scope.get('headers') or ():
        if key.lower() == name:
            return value.decode('latin1')
    return ''


def _cors_headers(scope):
    """同源请求不需要；本地开发（3000 → 8000）时补上，否则浏览器读不到响应。"""
    origin = _header(scope, 'origin')
    if not origin:
        return []
    allowed = getattr(settings, 'CORS_ALLOWED_ORIGINS', []) or []
    if origin in allowed or getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
        return [(b'access-control-allow-origin', origin.encode('latin1'))]
    return []


def _resolve_user(authorization):
    parts = (authorization or '').split()
    if len(parts) != 2 or parts[0].lower() not in ('bearer', 'jwt'):
        raise services.AiServiceError('请先登录后再使用 AI', 401, 'not_authenticated')

    try:
        token = AccessToken(parts[1])
    except TokenError:
        raise services.AiServiceError('登录状态已过期，请重新登录', 401, 'token_invalid')

    user = get_user_model().objects.filter(
        pk=token.get('user_id'), is_active=True).first()
    if user is None:
        raise services.AiServiceError('账号不可用，请重新登录', 401, 'token_invalid')
    return user


def _assert_rate_limit(user):
    """复用 DRF 的限流器，保证流式与非流式口径一致。"""
    from types import SimpleNamespace

    if not AiRateThrottle().allow_request(SimpleNamespace(user=user), None):
        raise services.AiServiceError('调用过于频繁，请稍后再试', 429, 'ai_rate_limited')


def _prepare(scope, raw_body):
    """同步执行：鉴权、限流、解析、取凭据。"""
    user = _resolve_user(_header(scope, 'authorization'))
    _assert_rate_limit(user)

    try:
        payload = json.loads(raw_body or b'{}')
    except (ValueError, TypeError):
        raise services.AiServiceError('请求体不是合法 JSON', 400, 'ai_bad_request')
    if not isinstance(payload, dict):
        raise services.AiServiceError('请求体必须是对象', 400, 'ai_bad_request')

    credential = services.get_credential(user)
    messages = services.normalize_messages(payload.get('messages'))
    return user, credential, messages, payload


# ---------------------------------------------------------------------------
# 响应
# ---------------------------------------------------------------------------

async def _send_json(send, status, payload, extra_headers=()):
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = [
        (b'content-type', b'application/json; charset=utf-8'),
        (b'content-length', str(len(body)).encode('ascii')),
        *extra_headers,
    ]
    await send({'type': 'http.response.start', 'status': status, 'headers': headers})
    await send({'type': 'http.response.body', 'body': body, 'more_body': False})


async def handle_stream(scope, receive, send):
    cors = _cors_headers(scope)

    raw_body = await _read_body(receive)
    if raw_body is None:  # 客户端还没发完就断了
        return

    try:
        user, credential, messages, payload = await sync_to_async(
            _prepare, thread_sensitive=True)(scope, raw_body)
    except services.AiServiceError as exc:
        await _send_json(send, exc.status, {'detail': exc.detail, 'code': exc.code}, cors)
        return

    model = payload.get('model') or credential.default_model or services.default_model()

    # 连通性校验放在写响应头之前：上游直接报错时前端能拿到正常的 JSON 错误
    try:
        upstream = await sync_to_async(
            services.open_stream, thread_sensitive=False)(credential, messages, payload)
    except services.AiServiceError as exc:
        await _send_json(send, exc.status, {'detail': exc.detail, 'code': exc.code}, cors)
        return

    await send({
        'type': 'http.response.start',
        'status': 200,
        'headers': [
            (b'content-type', b'text/event-stream; charset=utf-8'),
            (b'cache-control', b'no-cache, no-transform'),
            # 反代不缓冲，否则逐字输出会攒成一次性返回
            (b'x-accel-buffering', b'no'),
            *cors,
        ],
    })

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    stop = threading.Event()

    def push(item):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, item)
        except RuntimeError:
            # 事件循环已关闭（连接早就断了），丢弃即可
            stop.set()

    def worker():
        generator = services.iter_stream(upstream, user, model)
        try:
            for chunk in generator:
                if stop.is_set():
                    break
                push(chunk)
        except Exception as exc:  # noqa: BLE001 - 兜底，保证一定会发出终止信号
            push(services.sse_event({'type': 'error', 'message': str(exc)}))
        finally:
            # 提前退出时手动关闭，触发上游连接的 close()
            generator.close()
            push(None)

    threading.Thread(target=worker, name='ai-stream', daemon=True).start()

    async def watch_disconnect():
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                stop.set()
                return

    watcher = asyncio.create_task(watch_disconnect())

    try:
        while True:
            item = await queue.get()
            if item is None:
                break
            await send({
                'type': 'http.response.body',
                'body': item.encode('utf-8'),
                'more_body': True,
            })
        await send({'type': 'http.response.body', 'body': b'', 'more_body': False})
    finally:
        watcher.cancel()
        stop.set()
