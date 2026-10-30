"""验证码邮件与验证码生成。

邮件样式改坏不会报错，只会「发出去很难看」，所以这里断言的是结构：
内联样式是否还在、纯文本兜底是否存在、验证码是否真的出现在正文里。
"""
import re
import string

from django.core import mail
from django.test import TestCase, override_settings

from api.utlis import (
    CODE_ALPHABET,
    EMAIL_SCENES,
    get_random_code,
    send_verification_code_email,
)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class VerificationCodeEmailTests(TestCase):
    def setUp(self):
        mail.outbox = []

    def _send(self, scene='register', code='k7m2qp'):
        send_verification_code_email('user@example.com', code, scene=scene)
        self.assertEqual(len(mail.outbox), 1)
        return mail.outbox[0]

    def test_subject_differs_by_scene(self):
        self.assertEqual(self._send('register').subject, 'Kotae 注册验证码')
        mail.outbox = []
        self.assertEqual(self._send('reset').subject, 'Kotae 重置密码验证码')

    def test_html_and_plain_text_both_carry_the_code(self):
        message = self._send()
        self.assertEqual(message.to, ['user@example.com'])

        # 只发 HTML 会拉高进垃圾箱的概率，纯文本兜底必须存在
        self.assertIn('k7m2qp', message.body)

        self.assertEqual(len(message.alternatives), 1)
        html, mimetype = message.alternatives[0]
        self.assertEqual(mimetype, 'text/html')
        self.assertIn('k7m2qp', html)

    def test_html_keeps_inline_styles_and_site_palette(self):
        html = self._send().alternatives[0][0]

        # 关键视觉必须内联：QQ 邮箱 / Gmail 会丢掉 <head> 里的 <style>
        self.assertIn('border:2px solid #1A1A1A', html)
        self.assertIn('#e41b23', html)
        self.assertIn('#F9FAFB', html)
        self.assertIn('border-radius:18px', html)

        # 布局只能用 table，Outlook 不认 flex / grid
        self.assertNotIn('display:flex', html)
        self.assertNotIn('display:grid', html)

        # 模板不能把 Django 语法漏出去。注意 `{# #}` 只支持单行，
        # 写成多行会被原样渲染成正文——这条断言就是防这个的
        self.assertNotIn('{%', html)
        self.assertNotIn('{{', html)
        self.assertNotIn('{#', html)

    def test_html_uses_absolute_logo_and_site_url(self):
        html = self._send().alternatives[0][0]
        logo = re.search(r'<img src="([^"]+)"', html)
        self.assertIsNotNone(logo)
        self.assertTrue(logo.group(1).startswith('https://'))

        # 页脚链接必须是绝对地址，邮件客户端里相对路径打不开
        self.assertIn('href="https://kotae.cn"', html)

    def test_scene_copy_is_rendered(self):
        html = self._send('reset').alternatives[0][0]
        self.assertIn('重置你的密码', html)
        self.assertIn('账号安全 · 重置密码', html)
        self.assertIn(EMAIL_SCENES['reset']['intro'], html)

    def test_unknown_scene_falls_back_to_register(self):
        # 场景名拼错时不能抛异常把发信流程带崩，退回默认文案
        html = self._send(scene='nope').alternatives[0][0]
        self.assertIn(EMAIL_SCENES['register']['heading'], html)

    def test_from_address_keeps_display_name(self):
        self.assertTrue(self._send().from_email.startswith('Kotae <'))


class RandomCodeTests(TestCase):
    def test_code_is_alphanumeric_only(self):
        # 旧实现混了 string.punctuation，验证码会出现 < & " 这类字符
        for _ in range(50):
            code = get_random_code(6)
            self.assertEqual(len(code), 6)
            self.assertTrue(
                set(code) <= set(string.ascii_letters + string.digits),
                f'验证码出现了非字母数字字符：{code}',
            )

    def test_code_avoids_ambiguous_characters(self):
        for char in '0o1lIO':
            self.assertNotIn(char, CODE_ALPHABET)

    def test_codes_are_not_trivially_repeating(self):
        codes = {get_random_code(6) for _ in range(20)}
        self.assertGreater(len(codes), 15)
