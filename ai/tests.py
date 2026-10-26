import asyncio
import json
from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TransactionTestCase
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .asgi import handle_stream
from .crypto import encrypt
from .models import AiCredential, AiUsage

User = get_user_model()

UPSTREAM_PAYLOAD = {
    'model': 'qwen-flash',
    'choices': [{
        'message': {'role': 'assistant', 'content': '你好，世界'},
        'finish_reason': 'stop',
    }],
    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
}


class FakeResponse:
    """够用的 requests.Response 替身。"""

    def __init__(self, payload=None, status_code=200, lines=None):
        self._payload = payload or {}
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.reason = 'OK' if self.ok else 'ERROR'
        self._lines = lines or []
        self.closed = False

    @property
    def text(self):
        return json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload

    def iter_lines(self, decode_unicode=False):
        for line in self._lines:
            yield line

    def close(self):
        self.closed = True


class AiCredentialTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='aiuser', email='ai@example.com', password='pass1234')

    def test_requires_login(self):
        resp = self.client.get('/api/ai/credential/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        resp = self.client.post('/api/ai/chat/', {'messages': []}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_save_masks_and_encrypts(self):
        self.client.force_authenticate(user=self.user)

        resp = self.client.put(
            '/api/ai/credential/',
            {'api_key': 'sk-secret-abcdefghijklmn', 'default_model': 'qwen-plus'},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resp.data['configured'])
        # 明文和密文都不能出现在响应里
        self.assertNotIn('sk-secret', json.dumps(resp.data, default=str))
        self.assertEqual(resp.data['api_key_masked'], 'sk-s******klmn')

        stored = AiCredential.objects.get(user=self.user)
        self.assertNotEqual(stored.api_key, 'sk-secret-abcdefghijklmn')
        self.assertEqual(stored.default_model, 'qwen-plus')

    def test_default_model_is_qwen38_flash(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.put(
            '/api/ai/credential/', {'api_key': 'sk-default-000000'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['default_model'], 'qwen3.8-flash')
        self.assertEqual(
            AiCredential.objects.get(user=self.user).default_model, 'qwen3.8-flash')

    def test_update_without_key_keeps_existing(self):
        self.client.force_authenticate(user=self.user)
        self.client.put('/api/ai/credential/', {'api_key': 'sk-original-000000'}, format='json')
        before = AiCredential.objects.get(user=self.user).api_key

        resp = self.client.put('/api/ai/credential/', {'default_model': 'qwen-max'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        after = AiCredential.objects.get(user=self.user)
        self.assertEqual(after.api_key, before)
        self.assertEqual(after.default_model, 'qwen-max')

    def test_delete(self):
        self.client.force_authenticate(user=self.user)
        self.client.put('/api/ai/credential/', {'api_key': 'sk-abcdefgh-123456'}, format='json')
        resp = self.client.delete('/api/ai/credential/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(AiCredential.objects.filter(user=self.user).exists())


class AiChatTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='chatuser', email='chat@example.com', password='pass1234')
        self.client.force_authenticate(user=self.user)

    def _configure(self):
        self.client.put(
            '/api/ai/credential/',
            {'api_key': 'sk-test-1234567890', 'default_model': 'qwen-flash'},
            format='json',
        )

    def test_missing_key_returns_code(self):
        resp = self.client.post(
            '/api/ai/chat/', {'messages': [{'role': 'user', 'content': 'hi'}]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['code'], 'ai_key_missing')

    def test_empty_messages_rejected(self):
        self._configure()
        resp = self.client.post('/api/ai/chat/', {'messages': []}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['code'], 'ai_bad_request')

    @patch('ai.services.requests.post')
    def test_chat_success_records_usage(self, mock_post):
        self._configure()
        mock_post.return_value = FakeResponse(UPSTREAM_PAYLOAD)

        resp = self.client.post(
            '/api/ai/chat/',
            {'messages': [{'role': 'user', 'content': '打个招呼'}]},
            format='json',
        )

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['content'], '你好，世界')
        self.assertEqual(resp.data['usage']['totalTokens'], 15)

        usage = AiUsage.objects.get(user=self.user, model='qwen-flash')
        self.assertEqual(usage.requests, 1)
        self.assertEqual(usage.total_tokens, 15)

        # 发往上游的请求体要带上用户自己的 key
        headers = mock_post.call_args.kwargs['headers']
        self.assertEqual(headers['Authorization'], 'Bearer sk-test-1234567890')

    @patch('ai.services.requests.post')
    def test_upstream_401_maps_to_invalid_key(self, mock_post):
        self._configure()
        mock_post.return_value = FakeResponse(
            {'error': {'message': 'Incorrect API key provided'}}, status_code=401)

        resp = self.client.post(
            '/api/ai/chat/', {'messages': [{'role': 'user', 'content': 'hi'}]}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['code'], 'ai_key_invalid')
        self.assertFalse(AiUsage.objects.filter(user=self.user).exists())

    @patch('ai.services.requests.post')
    def test_chat_stream_emits_normalized_events(self, mock_post):
        self._configure()
        mock_post.return_value = FakeResponse(lines=[
            b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}',
            b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}',
            b'data: [DONE]',
        ])

        resp = self.client.post(
            '/api/ai/chat-stream/',
            {'messages': [{'role': 'user', 'content': '打招呼'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('text/event-stream', resp['Content-Type'])

        body = b''.join(resp.streaming_content).decode('utf-8')
        self.assertIn('"type": "delta"', body)
        self.assertIn('"content": "你"', body)
        self.assertIn('"type": "done"', body)

        usage = AiUsage.objects.get(user=self.user, model='qwen-flash')
        self.assertEqual(usage.total_tokens, 5)

    @patch('ai.services.requests.post')
    def test_stream_upstream_error_before_headers(self, mock_post):
        self._configure()
        mock_post.return_value = FakeResponse(
            {'message': 'AllocationQuota.FreeTierOnly'}, status_code=403)

        resp = self.client.post(
            '/api/ai/chat-stream/',
            {'messages': [{'role': 'user', 'content': 'hi'}]},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(resp.data['code'], 'ai_quota_exhausted')


class AiModelsAndQuotaTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='quota', email='quota@example.com', password='pass1234')
        self.client.force_authenticate(user=self.user)
        self.client.put('/api/ai/credential/', {'api_key': 'sk-test-abcdefgh'}, format='json')

    @patch('ai.services.requests.get')
    def test_models_falls_back_to_catalog(self, mock_get):
        mock_get.side_effect = requests.RequestException('boom')
        resp = self.client.get('/api/ai/models/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['source'], 'builtin')
        self.assertTrue(len(resp.data['models']) > 0)
        # 新用户不填模型时应当落到默认模型
        self.assertEqual(resp.data['default'], 'qwen3.8-flash')

    @patch('ai.services.requests.get')
    def test_models_prefers_upstream_and_filters_non_chat(self, mock_get):
        mock_get.return_value = FakeResponse({'data': [
            {'id': 'qwen-flash'}, {'id': 'text-embedding-v3'}, {'id': 'qwen-max'},
        ]})
        resp = self.client.get('/api/ai/models/')
        self.assertEqual(resp.data['source'], 'upstream')
        ids = [item['id'] for item in resp.data['models']]
        self.assertEqual(ids, ['qwen-flash', 'qwen-max'])

    def test_quota_is_scoped_to_user(self):
        AiUsage.objects.create(user=self.user, date='2026-10-26', model='qwen-flash',
                               requests=2, total_tokens=100)
        other = User.objects.create_user(
            username='other', email='other@example.com', password='pass1234')
        AiUsage.objects.create(user=other, date='2026-10-26', model='qwen-flash',
                               requests=9, total_tokens=999)

        resp = self.client.get('/api/ai/quota/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['total']['requests'], 2)
        self.assertEqual(resp.data['total']['totalTokens'], 100)


class FakeSend:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)


class FakeReceive:
    """第一次返回请求体，之后挂起（模拟连接还开着、没有 disconnect）。"""

    def __init__(self, body=b''):
        self._queue = [{'type': 'http.request', 'body': body, 'more_body': False}]

    async def __call__(self):
        if self._queue:
            return self._queue.pop(0)
        await asyncio.sleep(30)
        return {'type': 'http.disconnect'}


class AiStreamAsgiTests(TransactionTestCase):
    """原生 ASGI 流式接口：Django 4.0 的 StreamingHttpResponse 会阻塞事件循环，
    所以这条链路单独实现，必须单独验证。"""

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username='asgiuser', email='asgi@example.com', password='pass1234')
        AiCredential.objects.create(
            user=self.user,
            api_key=encrypt('sk-test-1234567890'),
            default_model='qwen-flash',
        )

    def _scope(self, token=None):
        headers = [(b'content-type', b'application/json')]
        if token:
            headers.append((b'authorization', f'Bearer {token}'.encode()))
        return {
            'type': 'http',
            'method': 'POST',
            'path': '/api/ai/chat-stream/',
            'headers': headers,
        }

    async def _call(self, scope, body, upstream):
        receive = FakeReceive(json.dumps(body).encode())
        send = FakeSend()
        with patch('ai.asgi.services.open_stream', return_value=upstream):
            await handle_stream(scope, receive, send)
        return send.messages

    def test_missing_token_returns_401(self):
        messages = asyncio.run(self._call(
            self._scope(), {'messages': [{'role': 'user', 'content': 'hi'}]},
            FakeResponse()))

        self.assertEqual(messages[0]['status'], 401)
        payload = json.loads(messages[1]['body'])
        self.assertEqual(payload['code'], 'not_authenticated')

    def test_streams_delta_and_done(self):
        token = str(AccessToken.for_user(self.user))
        upstream = FakeResponse(lines=[
            b'data: {"choices":[{"delta":{"content":"\xe4\xbd\xa0"}}]}',
            b'data: {"choices":[{"delta":{"content":"\xe5\xa5\xbd"}}]}',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}',
            b'data: [DONE]',
        ])

        messages = asyncio.run(self._call(
            self._scope(token), {'messages': [{'role': 'user', 'content': 'hi'}]}, upstream))

        start = messages[0]
        self.assertEqual(start['status'], 200)
        headers = dict(start['headers'])
        self.assertIn(b'text/event-stream', headers[b'content-type'])

        body = b''.join(
            m['body'] for m in messages if m['type'] == 'http.response.body'
        ).decode('utf-8')
        self.assertIn('"type": "delta"', body)
        self.assertIn('"type": "done"', body)

        usage = AiUsage.objects.get(user=self.user, model='qwen-flash')
        self.assertEqual(usage.total_tokens, 5)

    def test_upstream_error_before_headers(self):
        from .services import AiServiceError

        token = str(AccessToken.for_user(self.user))
        scope = self._scope(token)
        receive = FakeReceive(json.dumps(
            {'messages': [{'role': 'user', 'content': 'hi'}]}).encode())
        send = FakeSend()

        error = AiServiceError('额度用完', 402, 'ai_quota_exhausted')
        with patch('ai.asgi.services.open_stream', side_effect=error):
            asyncio.run(handle_stream(scope, receive, send))

        self.assertEqual(send.messages[0]['status'], 402)
        payload = json.loads(send.messages[1]['body'])
        self.assertEqual(payload['code'], 'ai_quota_exhausted')
