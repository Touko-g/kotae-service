"""AI 服务层：消息归一化、上游调用、SSE 归一化、用量记账、模型探测。

设计原则：
- 上游协议只在这一层出现，换成别家 OpenAI 兼容服务时改这里即可；
- 所有失败都抛 AiServiceError，由视图统一转成 {detail, code} 响应；
- 用量记账失败绝不影响对话本身。
"""
import hashlib
import json
import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.db.models import F, Sum
from django.utils import timezone

from .crypto import CredentialCryptoError, decrypt, mask_api_key  # noqa: F401
from .models import AiCredential, AiUsage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

ALLOWED_ROLES = ('system', 'user', 'assistant')
MAX_CONTENT_LENGTH = 24000
MAX_MESSAGES = 40
MODELS_CACHE_TTL = 600
MODELS_PROBE_TIMEOUT = 4

# 内置模型清单：DashScope 兼容模式的 /models 不是稳定接口，
# 探测不到时用它兜底，保证选择框永远有内容
MODEL_CATALOG = [
    {'id': 'qwen3.8-flash', 'label': 'qwen3.8-flash', 'desc': '默认模型，速度与质量均衡', 'recommended': True},
    {'id': 'qwen-flash', 'label': 'qwen-flash', 'desc': '快而便宜，日常写作够用'},
    {'id': 'qwen-plus', 'label': 'qwen-plus', 'desc': '能力与成本均衡'},
    {'id': 'qwen-max', 'label': 'qwen-max', 'desc': '质量最好，速度慢一些'},
    {'id': 'qwen-long', 'label': 'qwen-long', 'desc': '超长上下文'},
    {'id': 'qwen-turbo', 'label': 'qwen-turbo', 'desc': '极速，适合短文本'},
]

# 命中这些关键词的是向量 / 重排 / 语音 / 图像模型，走 chat/completions 必 502
NON_CHAT_HINTS = (
    'rerank', 'embedding', 'embed', 'tts', 'asr', 'paraformer',
    'sambert', 'cosyvoice', 'sensevoice', 'wanx', 'stable-diffusion', 'ocr',
)

# extra 里不允许覆盖的字段：改掉它们会破坏归一化协议
PROTECTED_EXTRA_KEYS = ('messages', 'stream', 'stream_options')


class AiServiceError(Exception):
    """带 HTTP 状态与机器可读 code 的业务异常。"""

    def __init__(self, detail, status=400, code='ai_error'):
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.code = code


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

def _clamp(value, low, high):
    return max(low, min(high, value))


def _to_number(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def default_base_url():
    return getattr(settings, 'AI_DEFAULT_BASE_URL',
                   'https://dashscope.aliyuncs.com/compatible-mode/v1')


def default_model():
    return getattr(settings, 'AI_DEFAULT_MODEL', 'qwen3.8-flash')


def upstream_timeout():
    """(连接超时, 读取超时) —— 流式时读取超时是「两个分片之间」的最长间隔。"""
    return (
        _clamp(_to_number(getattr(settings, 'AI_CONNECT_TIMEOUT', 10), 10), 1, 60),
        _clamp(_to_number(getattr(settings, 'AI_TIMEOUT', 120), 120), 5, 600),
    )


# ---------------------------------------------------------------------------
# 凭据
# ---------------------------------------------------------------------------

def get_credential(user, required=True):
    """取用户凭据；未配置或解不开时按「未配置」处理。"""
    try:
        credential = AiCredential.objects.filter(user=user).first()
    except Exception:  # 数据库异常不该伪装成「没配 key」
        logger.exception('读取 AI 凭据失败 user=%s', user.pk)
        raise AiServiceError('AI 服务暂时不可用', 500, 'ai_internal_error')

    if credential is None or not credential.enabled:
        if required:
            raise AiServiceError(
                '请先配置你自己的 AI API Key', 400, 'ai_key_missing')
        return None

    try:
        decrypt(credential.api_key)
    except CredentialCryptoError as exc:
        if required:
            raise AiServiceError(str(exc), 400, 'ai_key_invalid')
        return None

    return credential


def plain_api_key(credential):
    return decrypt(credential.api_key)


# ---------------------------------------------------------------------------
# 请求体归一化
# ---------------------------------------------------------------------------

def normalize_messages(raw):
    if not isinstance(raw, list):
        raise AiServiceError('messages 必须是数组', 400, 'ai_bad_request')

    messages = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get('role') if item.get('role') in ALLOWED_ROLES else 'user'
        content = item.get('content')
        content = content if isinstance(content, str) else ''
        content = content[:MAX_CONTENT_LENGTH]
        if content.strip():
            messages.append({'role': role, 'content': content})

    if not messages:
        raise AiServiceError('messages 不能为空', 400, 'ai_bad_request')

    # 超长对话只保留最近的若干条
    return messages[-MAX_MESSAGES:]


def _with_system_prompt(messages, system):
    prompt = system.strip()[:MAX_CONTENT_LENGTH] if isinstance(system, str) else ''
    if not prompt or (messages and messages[0].get('role') == 'system'):
        return messages
    return [{'role': 'system', 'content': prompt}, *messages]


def build_upstream_body(credential, messages, options, stream):
    body = {
        'model': options.get('model') or credential.default_model or default_model(),
        'messages': _with_system_prompt(messages, options.get('system')),
        'temperature': _clamp(
            _to_number(options.get('temperature'), _to_number(
                getattr(settings, 'AI_TEMPERATURE', 0.7), 0.7)), 0, 2),
        'max_tokens': int(_clamp(
            _to_number(options.get('maxTokens'), _to_number(
                getattr(settings, 'AI_MAX_TOKENS', 2048), 2048)), 1, 8192)),
        'stream': stream,
    }

    if options.get('topP') is not None:
        body['top_p'] = _clamp(_to_number(options.get('topP'), 0.8), 0, 1)

    if stream:
        # 要求上游在最后一个分片带上 usage，否则流式拿不到用量
        body['stream_options'] = {'include_usage': True}

    extra = options.get('extra')
    if isinstance(extra, dict):
        for key, value in extra.items():
            if key not in PROTECTED_EXTRA_KEYS:
                body[key] = value

    return body


# ---------------------------------------------------------------------------
# 上游调用
# ---------------------------------------------------------------------------

def _chat_endpoint(credential):
    base = (credential.base_url or default_base_url()).strip().rstrip('/')
    return f'{base}/chat/completions'


def _auth_headers(credential):
    return {
        'Authorization': f'Bearer {plain_api_key(credential)}',
        'Content-Type': 'application/json',
    }


def _read_upstream_error(resp):
    """把上游错误体压成一行可读文案，避免整段 HTML 塞进响应。"""
    text = (resp.text or '')[:2000]
    try:
        data = json.loads(text)
        return str(
            (data.get('error') or {}).get('message')
            or data.get('message')
            or data.get('code')
            or text[:300]
        )
    except (ValueError, TypeError):
        return text[:300] or resp.reason or f'HTTP {resp.status_code}'


def _error_from_upstream(resp):
    detail = _read_upstream_error(resp)
    status = resp.status_code

    # 「免费额度用完即停」会以 403 返回，但它不是密钥问题：
    # 必须排在 401/403 判断之前，否则会被误报成「Key 无效」
    if status == 402 or 'FreeTierOnly' in detail or 'AllocationQuota' in detail:
        return AiServiceError(
            'AI 免费额度已用尽（AllocationQuota.FreeTierOnly）—— 请到百炼控制台'
            '关闭「免费额度用完即停」或充值',
            402,
            'ai_quota_exhausted',
        )

    if status in (401, 403):
        return AiServiceError(
            'API Key 无效或没有访问权限，请到设置里检查', 400, 'ai_key_invalid')

    if status == 429:
        return AiServiceError('调用过于频繁，请稍后再试', 429, 'ai_rate_limited')

    return AiServiceError(f'AI 上游错误：{detail}', 502, 'ai_upstream_error')


def _post(credential, body, stream):
    try:
        return requests.post(
            _chat_endpoint(credential),
            headers=_auth_headers(credential),
            json=body,
            timeout=upstream_timeout(),
            stream=stream,
        )
    except requests.RequestException as exc:
        raise AiServiceError(f'无法连接 AI 服务：{exc}', 502, 'ai_unreachable')


def _map_usage(usage):
    if not isinstance(usage, dict):
        return None
    return {
        'promptTokens': int(_to_number(usage.get('prompt_tokens'), 0)),
        'completionTokens': int(_to_number(usage.get('completion_tokens'), 0)),
        'totalTokens': int(_to_number(usage.get('total_tokens'), 0)),
    }


def request_chat(credential, messages, options):
    """非流式：一次性拿到完整回复。"""
    resp = _post(credential, build_upstream_body(credential, messages, options, False), stream=False)
    if not resp.ok:
        raise _error_from_upstream(resp)

    try:
        data = resp.json()
    except ValueError:
        raise AiServiceError('AI 返回了无法解析的内容', 502, 'ai_bad_upstream')

    choice = (data.get('choices') or [{}])[0]
    model = data.get('model') or options.get('model') or credential.default_model
    usage = _map_usage(data.get('usage'))

    record_usage(credential.user, model, usage)

    return {
        'content': (choice.get('message') or {}).get('content') or '',
        'model': model,
        'usage': usage,
        'finishReason': choice.get('finish_reason'),
    }


def open_stream(credential, messages, options):
    """建立流式上游连接。

    这里刻意把「连通性校验」和「产出分片」拆开：连不上或上游直接报错时
    还没写 SSE 头，视图可以正常返回一个 JSON 错误，前端能读到原因。
    """
    resp = _post(credential, build_upstream_body(credential, messages, options, True), stream=True)
    if not resp.ok:
        resp.close()
        raise _error_from_upstream(resp)
    return resp


def sse_event(payload):
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


def iter_stream(resp, user, model):
    """把上游 SSE 归一化成 {type: delta|done|error} 事件流。"""
    usage = None
    finish_reason = None

    try:
        for raw in resp.iter_lines(decode_unicode=False):
            if not raw:
                continue
            line = raw.decode('utf-8', errors='ignore').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if not payload or payload == '[DONE]':
                continue
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue

            choice = (chunk.get('choices') or [{}])[0]
            delta = (choice.get('delta') or {}).get('content')
            if isinstance(delta, str) and delta:
                yield sse_event({'type': 'delta', 'content': delta})
            if choice.get('finish_reason'):
                finish_reason = choice['finish_reason']
            if chunk.get('usage'):
                usage = _map_usage(chunk['usage'])
    except requests.RequestException as exc:
        logger.warning('AI 流式中断 user=%s: %s', user.pk, exc)
        yield sse_event({'type': 'error', 'message': f'AI 服务中断：{exc}'})
        return
    finally:
        resp.close()

    yield sse_event({
        'type': 'done',
        'model': model,
        'usage': usage,
        'finishReason': finish_reason,
    })
    record_usage(user, model, usage)


# ---------------------------------------------------------------------------
# 用量记账
# ---------------------------------------------------------------------------

def _today():
    """项目是 USE_TZ=False，timezone.localdate() 会因 naive datetime 报错，
    用 now().date() 在两种时区模式下都成立。"""
    return timezone.now().date()


def record_usage(user, model, usage):
    """累加一条用量。写库失败只丢统计，不能影响对话。"""
    try:
        today = _today()
        name = (model or 'unknown')[:100]
        usage = usage or {}

        AiUsage.objects.get_or_create(
            user=user, date=today, model=name,
            defaults={
                'requests': 0,
                'prompt_tokens': 0,
                'completion_tokens': 0,
                'total_tokens': 0,
            },
        )
        # 用 F 表达式原子累加，避免并发请求互相覆盖
        AiUsage.objects.filter(user=user, date=today, model=name).update(
            requests=F('requests') + 1,
            prompt_tokens=F('prompt_tokens') + int(usage.get('promptTokens') or 0),
            completion_tokens=F('completion_tokens') + int(usage.get('completionTokens') or 0),
            total_tokens=F('total_tokens') + int(usage.get('totalTokens') or 0),
        )
    except Exception:
        logger.exception('写入 AI 用量失败 user=%s', getattr(user, 'pk', None))


def read_quota(user):
    today = _today()

    def _sum(qs):
        return qs.aggregate(
            requests=Sum('requests'),
            promptTokens=Sum('prompt_tokens'),
            completionTokens=Sum('completion_tokens'),
            totalTokens=Sum('total_tokens'),
        )

    today_rows = AiUsage.objects.filter(user=user, date=today)
    today_agg = _sum(today_rows)
    by_model = {
        row['model']: {'requests': row['requests'], 'totalTokens': row['total_tokens']}
        for row in today_rows.values('model').annotate(
            requests=Sum('requests'), total_tokens=Sum('total_tokens'))
    }

    all_rows = AiUsage.objects.filter(user=user)
    total_agg = _sum(all_rows)
    days = all_rows.values('date').distinct().count()

    return {
        'today': {
            'date': today.isoformat(),
            'requests': today_agg['requests'] or 0,
            'promptTokens': today_agg['promptTokens'] or 0,
            'completionTokens': today_agg['completionTokens'] or 0,
            'totalTokens': today_agg['totalTokens'] or 0,
            'byModel': by_model,
        },
        'total': {
            'days': days,
            'requests': total_agg['requests'] or 0,
            'totalTokens': total_agg['totalTokens'] or 0,
        },
        # 官方免费额度没有公开 API，只能给控制台外链
        'officialAvailable': False,
        'consoleUrl': 'https://bailian.console.aliyun.com/cn-beijing/costing-balance/free-quota',
    }


# ---------------------------------------------------------------------------
# 模型列表
# ---------------------------------------------------------------------------

def is_chat_model(model_id):
    lower = model_id.lower()
    return not any(hint in lower for hint in NON_CHAT_HINTS)


def _merge_with_catalog(ids):
    catalog = {item['id']: item for item in MODEL_CATALOG}
    seen, models = set(), []
    for model_id in ids:
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(catalog.get(model_id, {'id': model_id, 'label': model_id}))
    return models


def _probe_upstream_models(credential):
    """返回可用对话模型 id；上游不可用时返回 None（而不是空列表）。"""
    base = (credential.base_url or default_base_url()).strip().rstrip('/')
    try:
        resp = requests.get(
            f'{base}/models',
            headers={'Authorization': f'Bearer {plain_api_key(credential)}'},
            timeout=MODELS_PROBE_TIMEOUT,
        )
        if not resp.ok:
            return None
        data = resp.json()
        ids = [str(item.get('id') or '') for item in (data.get('data') or [])]
        chat = [model_id for model_id in ids if model_id and is_chat_model(model_id)]
        return chat or None
    except (requests.RequestException, ValueError, AttributeError):
        return None


def fetch_models(credential):
    """模型列表。缓存按用户 + key 指纹分桶，避免 A 的清单被 B 读到。"""
    fingerprint = hashlib.sha256(
        plain_api_key(credential).encode('utf-8')).hexdigest()[:12]
    cache_key = f'ai:models:{credential.user_id}:{fingerprint}'

    cached = cache.get(cache_key)
    if cached:
        return cached

    ids = _probe_upstream_models(credential)
    value = {
        'models': _merge_with_catalog(ids) if ids else MODEL_CATALOG,
        'source': 'upstream' if ids else 'builtin',
        'default': credential.default_model or default_model(),
    }
    cache.set(cache_key, value, MODELS_CACHE_TTL)
    return value
