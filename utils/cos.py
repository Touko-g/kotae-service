#! /usr/bin/env python3
# -*- coding: utf-8 -*-
# @Time : 2021/8/23 18:32
# @Author : WangHaoRan
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from sts.sts import Sts

from dotenv import load_dotenv
import os

load_dotenv()


@api_view(["GET"])
@permission_classes([AllowAny])
def cos_key(request):
    config = {
        'url': 'https://sts.tencentcloudapi.com/',
        # 域名，非必须，默认为 sts.tencentcloudapi.com
        'domain': 'sts.tencentcloudapi.com',
        # 临时密钥有效时长，单位是秒
        'duration_seconds': 7200,
        'secret_id': os.getenv("secret_id"),
        # 固定密钥
        'secret_key': os.getenv("secret_key"),

        # 换成你的 bucket
        'bucket': 'chen-1302611521',
        # 'bucket': 'jkexpress-1307254482',
        # 换成 bucket 所在地区
        'region': 'ap-nanjing',
        # 'region': 'ap-shanghai',
        # 这里改成允许的路径前缀，可以根据自己网站的用户登录态判断允许上传的具体路径
        # 例子： a.jpg 或者 a/* 或者 * (使用通配符*存在重大安全风险, 请谨慎评估使用)
        'allow_prefix': '*',
        # 密钥的权限列表。简单上传和分片需要以下的权限，其他权限列表请看 https://cloud.tencent.com/document/product/436/31923
        'allow_actions': [
            # 简单上传
            'name/cos:PutObject',
            'name/cos:PostObject',
            # 分片上传
            'name/cos:InitiateMultipartUpload',
            'name/cos:ListMultipartUploads',
            'name/cos:ListParts',
            'name/cos:UploadPart',
            'name/cos:CompleteMultipartUpload',
            "name/cos:GetService",
            "name/cos:GetObject",
        ],
    }
    try:
        sts = Sts(config)
        # print('get data : ' + json.dumps(dict(sts.get_credential()), indent=4))
        return Response(status=status.HTTP_200_OK, data=sts.get_credential())
    except Exception as e:
        print(e)
        return Response(status=status.HTTP_400_BAD_REQUEST, data={'detail': f'{e}'})
