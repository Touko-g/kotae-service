"""验证码生成与邮件发送。

邮件正文用模板渲染（`templates/email/`），不再把 HTML 拼在函数里：
模板要跟着站点主题走，内联样式改起来才有地方改。
"""
from random import sample
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

# 验证码邮件的场景文案。新增场景（改密、注销确认……）只在这里加一项，
# 模板和发送逻辑都不用动。
EMAIL_SCENES = {
    'register': {
        'subject': 'Kotae 注册验证码',
        'scene_label': '账号安全 · 注册',
        'heading': '验证你的邮箱',
        'intro': '欢迎加入 Kotae。请在注册页面输入下面的验证码，完成邮箱验证。',
    },
    'reset': {
        'subject': 'Kotae 重置密码验证码',
        'scene_label': '账号安全 · 重置密码',
        'heading': '重置你的密码',
        'intro': '我们收到了重置 Kotae 账号密码的请求。请在重置页面输入下面的验证码继续操作。',
    },
}
DEFAULT_SCENE = 'register'

# 去掉 0/o、1/l/I 这类易混淆字符：验证码要靠用户手抄或复制，
# 混进去只会增加「明明输对了却提示错误」的投诉。54 个字符取 6 位，
# 组合数约 2.5e10，配合一次性使用足够。
CODE_ALPHABET = '23456789abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ'


def get_random_code(length):
    """生成验证码。

    只取字母和数字。旧实现用的是 `ascii_letters + digits + punctuation`，
    验证码里会出现 `<`、`&`、`"` 这类字符——邮件里要靠模板转义才不破坏排版，
    用户也很难分辨是 1 还是 l。
    """
    return ''.join(sample(CODE_ALPHABET, length))


def send_verification_code_email(email, code, scene=DEFAULT_SCENE):
    """发送验证码邮件，返回实际发出的邮件数（0/1）。

    纯文本 + HTML 双版本：只发 HTML 会显著提高进垃圾箱的概率，
    纯文本也保证在关闭 HTML 的客户端里仍能读到验证码。
    """
    conf = EMAIL_SCENES.get(scene) or EMAIL_SCENES[DEFAULT_SCENE]
    site_url = settings.SITE_URL.rstrip('/')
    context = {
        **conf,
        'code': code,
        'logo_url': settings.EMAIL_LOGO_URL,
        'site_url': site_url,
        # 页脚只显示域名，避免长链接把整行撑开
        'site_host': urlparse(site_url).netloc or site_url,
    }

    message = EmailMultiAlternatives(
        subject=conf['subject'],
        body=render_to_string('email/verification_code.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(
        render_to_string('email/verification_code.html', context), 'text/html')
    return message.send()
