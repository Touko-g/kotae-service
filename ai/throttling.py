from rest_framework.throttling import UserRateThrottle


class AiRateThrottle(UserRateThrottle):
    """按登录用户限流。

    原来是按 IP 的内存表，迁到 Django 后改成 DRF 的缓存计数：
    既天然按用户隔离（同一出口 IP 的多个用户互不影响），
    也不会因为多 worker 部署而各算一份。
    """

    scope = 'ai'
