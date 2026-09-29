from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class WishApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', email='tester@example.com', password='pass1234')
        self.other = User.objects.create_user(username='other', email='other@example.com', password='pass1234')
        self.client.force_authenticate(user=self.user)

    def test_create_and_list(self):
        resp = self.client.post('/api/wish/', {'title': '去看极光'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.get('/api/wish/')
        self.assertEqual(resp.data['count'], 1)

    def test_complete_updates_time(self):
        wish_id = self.client.post('/api/wish/', {'title': '学会冲浪'}, format='json').data['id']
        resp = self.client.patch(f'/api/wish/{wish_id}/', {'completed': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['complete_time'])
        resp = self.client.patch(f'/api/wish/{wish_id}/', {'completed': False}, format='json')
        self.assertIsNone(resp.data['complete_time'])

    def test_filter_completed(self):
        self.client.post('/api/wish/', {'title': 'A'}, format='json')
        self.client.post('/api/wish/', {'title': 'B'}, format='json')
        self.client.get('/api/wish/?completed=false')

    def test_public_visible_but_only_owner_can_edit(self):
        wish_id = self.client.post('/api/wish/', {'title': '公开心愿'}, format='json').data['id']
        # 其他登录用户可查看全部心愿
        self.client.force_authenticate(user=self.other)
        resp = self.client.get(f'/api/wish/{wish_id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get('/api/wish/').data['count'], 1)
        # 但不能修改/删除他人心愿
        self.assertEqual(self.client.patch(f'/api/wish/{wish_id}/', {'completed': True}, format='json').status_code,
                         status.HTTP_403_FORBIDDEN)
        self.assertEqual(self.client.delete(f'/api/wish/{wish_id}/').status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_can_read_not_write(self):
        self.client.post('/api/wish/', {'title': '游客可见'}, format='json')
        self.client.force_authenticate(user=None)
        # 未登录可浏览列表和详情
        resp = self.client.get('/api/wish/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        # 未登录不能创建
        self.assertEqual(self.client.post('/api/wish/', {'title': '游客心愿'}, format='json').status_code,
                         status.HTTP_401_UNAUTHORIZED)

    def test_list_exposes_user_info(self):
        resp = self.client.post('/api/wish/', {'title': '带作者信息'}, format='json')
        self.assertEqual(resp.data['user_info']['username'], 'tester')

    def test_delete_removes_record(self):
        wish_id = self.client.post('/api/wish/', {'title': '删掉我'}, format='json').data['id']
        resp = self.client.delete(f'/api/wish/{wish_id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        from wishlist.models import Wish
        # 硬删除：记录彻底不存在，任何人（含超管）都不会再查到
        self.assertFalse(Wish.objects.filter(pk=wish_id).exists())
        self.assertEqual(self.client.get('/api/wish/').data['count'], 0)
        # 重复删除返回 404 而非报错
        self.assertEqual(self.client.delete(f'/api/wish/{wish_id}/').status_code, status.HTTP_404_NOT_FOUND)
