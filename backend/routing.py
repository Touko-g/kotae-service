import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

# 允许直接以 `daphne backend.routing:application` 启动（此时没人替我们设这个变量）
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 必须先完成 django.setup()：下面的 chat / ai 模块都会导入 models
django_asgi = get_asgi_application()

import chat.routing  # noqa: E402
from ai.asgi import AiHttpRouter  # noqa: E402

application = ProtocolTypeRouter({
    # HTTP 走自定义路由：AI 流式接口单独处理，其余请求原样交给 Django
    # （原因见 ai/asgi.py 顶部注释：Django 4.0 的 ASGI 流式迭代会阻塞事件循环）
    "http": AiHttpRouter(django_asgi),
    "websocket": AuthMiddlewareStack(
        URLRouter(chat.routing.websocket_urlpatterns)
    ),
})
