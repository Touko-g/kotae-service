import json
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer
from .models import Online, Chat
from asgiref.sync import async_to_sync


class ChatRoomConsumer(WebsocketConsumer):
    def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

        # 必须是已登录用户，身份以服务端 session 为准，不信任客户端传参
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            self.close(code=4001)
            return

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def disconnect(self, close_code):
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name,
            self.channel_name
        )

    def receive(self, text_data):
        text_data_json = json.loads(text_data)
        if 'type' in text_data_json.keys():
            type_id = text_data_json['type']
        else:
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_error',
                    'error': 'type is Required'
                }
            )
            return
        # 锁定当前连接对应的登录用户，join/leave/message 均以此为准
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            return
        if type_id == 'join':
            obj, _ = Online.objects.get_or_create(user=user)
            obj.online = True
            obj.save()
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_join',
                    'user': user.username,
                    'status': 'join'
                }
            )
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_online',
                    'online': Online.objects.filter(online=True).count()
                }
            )
        elif type_id == 'message':
            message = text_data_json.get('message', '')
            # username/avatar 不再信任客户端传值，一律取当前登录用户
            Chat.objects.create(user=user, message=message)

            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_message',
                    'message': message,
                    'username': user.username,
                    'avatar': user.avatar
                }
            )
        elif type_id == 'leave':
            obj, _ = Online.objects.get_or_create(user=user)
            obj.online = False
            obj.save()
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_leave',
                    'user': user.username,
                    'status': 'leave'
                }
            )
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_online',
                    'online': Online.objects.filter(online=True).count()
                }
            )
        else:
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_error',
                    'error': 'type is not found'
                }
            )

    def chatroom_message(self, event):
        message = event['message']
        username = event['username']
        avatar = event['avatar']
        self.send(text_data=json.dumps({
            'message': message,
            'username': username,
            'avatar': avatar
        }))

    def chatroom_join(self, event):
        user = event['user']
        status = event['status']
        self.send(text_data=json.dumps({
            'user': user,
            'status': status
        }))

    def chatroom_leave(self, event):
        user = event['user']
        status = event['status']
        self.send(text_data=json.dumps({
            'user': user,
            'status': status
        }))

    def chatroom_online(self, event):
        online = event['online']
        self.send(text_data=json.dumps({
            'online': online,
        }))

    def chatroom_error(self, event):
        error = event['error']
        self.send(text_data=json.dumps({
            'error': error,
        }))


pass
