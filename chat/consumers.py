import json
from channels.generic.websocket import AsyncWebsocketConsumer, WebsocketConsumer
from .models import Online, Chat
from asgiref.sync import async_to_sync


class ChatRoomConsumer(WebsocketConsumer):
    def connect(self):
        self.room_name = self.scope['url_route']['kwargs']['room_name']
        self.room_group_name = 'chat_%s' % self.room_name

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
        if type_id == 'join':
            user_id = text_data_json['user']
            obj = Online.objects.get(user_id=user_id)
            obj.online = True
            obj.save()
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_join',
                    'user': obj.user.username,
                    'status': 'join'
                }
            )
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_online',
                    'online': len(Online.objects.filter(online=True))
                }
            )
        elif type_id == 'message':
            message = text_data_json['message']
            username = text_data_json['username']
            avatar = text_data_json['avatar']
            obj = Online.objects.get(user__username=username)
            Chat.objects.create(user=obj.user, message=message)

            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_message',
                    'message': message,
                    'username': username,
                    'avatar': avatar
                }
            )
        elif type_id == 'leave':
            user_id = text_data_json['user']
            obj = Online.objects.get(user_id=user_id)
            obj.online = False
            obj.save()
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_leave',
                    'user': obj.user.username,
                    'status': 'leave'
                }
            )
            async_to_sync(self.channel_layer.group_send)(
                self.room_group_name,
                {
                    'type': 'chatroom_online',
                    'online': len(Online.objects.filter(online=True))
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
