from random import choice

from django.core.mail import send_mail
from django.conf import settings


def get_random_code(length):
    import random
    import string
    return ''.join(random.sample(string.ascii_letters + string.digits + string.punctuation, length))


def send_email_mes(message, email, code):
    send_mail(subject="来自 Kotae 的账号验证码",
              message=message,
              from_email=settings.EMAIL_HOST_USER,
              recipient_list=[email],
              fail_silently=False,
              html_message=f'''
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>验证码邮件</title>
</head>
<body style="   font-family: Arial, sans-serif;
            line-height: 1.6;
            background-color: #f6f6f6;
            margin: 0;
            padding: 0;">
<div style="            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #ffffff;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);">
    <div style="display: flex;align-items: center;margin-bottom: 20px">
        <img src="https://chen-1302611521.cos.ap-nanjing.myqcloud.com/logo.png" alt="" style="width: 60px;height: 60px">
        <span style="font-size: 40px;font-weight: bolder;margin-left: 20px;color: #EC1C24">Kotae</span>
    </div>

    <h1 style="            color: #333333;">{message}邮件</h1>
    <p style="    color: #555555;">尊敬的用户，您的验证码是：<span style="   font-size: 24px;
            font-weight: bold;
            color: #EC1C24;">{code}</span></p>
    <p class="footer" style="
            padding: 10px 0;
            color: #777777;">如果您没有请求此验证码，请忽略此邮件。</p>
</div>
</body>
</html>

''')


def generate_code(self):
    """
    生成6位数验证码 防止破解
    :return:
    """
    seeds = "1234567890abcdefghijklmnopqrstuvwxyz"
    random_str = []
    for i in range(6):
        random_str.append(choice(seeds))
    return "".join(random_str)
