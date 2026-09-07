from .models import Tag, Article, Like, Comment, Search, Notice, Photo
from common.models import User
from rest_framework import serializers
from common.serializers import UserSerializer
from drf_writable_nested.serializers import WritableNestedModelSerializer


class SearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Search
        fields = ('id', 'name', 'hot')


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'hot')


class LikeSerialize(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField(read_only=True)
    article_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Like
        fields = ('id', 'user_info', 'article', 'article_info', 'create_time')
        extra_kwargs = {
            'create_time': {'read_only': True},
        }

    def get_user_info(self, obj):
        if not obj.user:
            return {}
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar
        }

    def get_article_info(self, obj):
        if not obj.article:
            return {}
        article = obj.article
        return {
            "id": article.id,
            "user": article.user.username,
            "avatar": article.user.avatar,
            "title": article.title
        }


class CommentSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField(read_only=True)
    article_info = serializers.SerializerMethodField(read_only=True)
    comment_replies = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Comment
        fields = ('id', 'user_info', 'article',
                  'article_info', 'reply', 'content', 'comment_replies', 'ip_address', 'create_time')

    def get_user_info(self, obj):
        if not obj.user:
            return {}
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar
        }

    def get_article_info(self, obj):
        if not obj.article:
            return {}
        article = obj.article
        obj = Comment.objects.filter(article=article.id).filter(reply=None)
        return {
            "id": article.id,
            "comments": article.comments,
            "len": len(obj),
            "title": article.title
        }

    def get_comment_replies(self, obj):
        if not obj.comment_reply:
            return []
        replies = obj.comment_reply.all()
        comments = Comment.objects.filter(article=obj.article.id)
        results = []
        for i in comments:
            if i.reply_id is not None:
                if i.reply_id == obj.id:
                    results.append({
                        'id': i.id,
                        'content': i.content,
                        'reply_user': None,
                        'user_info': {
                            'id': i.user.id,
                            'username': i.user.username,
                            'avatar': i.user.avatar,
                        },
                        'ip_address': i.ip_address,
                        'create_time': i.create_time
                    })
                for j in results:
                    if j.get('id') == i.reply_id:
                        results.append({
                            'id': i.id,
                            'content': i.content,
                            'reply_user': i.reply.user.username,
                            'user_info': {
                                'id': i.user.id,
                                'username': i.user.username,
                                'avatar': i.user.avatar,
                            },
                            'ip_address': i.ip_address,
                            'create_time': i.create_time
                        })
        return results
        # return [{
        #     'id': reply.id,
        #     'content': reply.content,
        #     'reply_user': reply.reply.user.username,
        #     'user_info': {
        #         'id': reply.user.id,
        #         'username': reply.user.username,
        #         'avatar': reply.user.avatar,
        #     },
        #     'create_time': reply.create_time
        # } for reply in replies]


class NoticeSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField(read_only=True)
    recipient_info = serializers.SerializerMethodField(read_only=True)
    target_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Notice
        fields = (
            'id', 'user_info', 'recipient_info', 'verb', 'target_info', 'content', 'reply_content', 'read',
            'create_time')

    def get_user_info(self, obj):
        if not obj.user:
            return {}
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar
        }

    def get_recipient_info(self, obj):
        if not obj.recipient:
            return {}
        recipient = obj.recipient
        return {
            "id": recipient.id,
            "username": recipient.username,
            "avatar": recipient.avatar
        }

    def get_target_info(self, obj):
        if not obj.target:
            return {}
        article = obj.target
        return {
            "id": article.id,
            "title": article.title,
        }


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


# class TagInlineSerializer(serializers.Serializer):
#     name = serializers.CharField(read_only=True)


class ArticleSerializer(WritableNestedModelSerializer):
    tag = TagSerializer(many=True)
    owner = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Article
        fields = ['id', 'title', 'owner', 'tag', 'likes', 'content', 'views', 'comments', 'public', 'create_time',
                  'update_time']

    def get_owner(self, obj):
        if not obj.user:
            return {}
        else:
            user = obj.user
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "about": user.about,
                "avatar": user.avatar,
                "article": len(Article.objects.filter(user_id=obj.id)),
            }

    # def to_representation(self, instance):
    #     ret = super().to_representation(instance)
    #     # ret["author"] = User.objects.get(pk=ret["author"])
    #     try:
    #         print(ret)
    #         author = User.objects.get(pk=ret["author"])
    #         ret['author'] = UserSerializer(author).data
    #     except Exception as e:
    #         ret['author'] = UserSerializer(None).data
    #     return ret
    #

    def get_or_create_tags(self, tags):
        results = []
        if len(tags):
            for tag in tags:
                tag_instance, created = Tag.objects.get_or_create(name=tag["name"])
                results.append(tag_instance)
            return results
        else:
            raise serializers.ValidationError({"tag": "不允许为空"})

    def create(self, validated_data):
        tags = validated_data.pop('tag', [])
        article = Article.objects.create(**validated_data)
        article.tag.set(self.get_or_create_tags(tags))
        article.save()
        return article

    def update(self, instance, validated_data):
        tags = validated_data.pop('tag', [])
        instance.title = validated_data.get('title', instance.title)
        instance.content = validated_data.get('content', instance.content)
        instance.tag.set(self.get_or_create_tags(tags))
        instance.save()
        return instance


class PhotoSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Photo
        fields = ('id', 'user_info', 'name', 'picture', 'create_time', 'update_time')

    def get_user_info(self, obj):
        if not obj.user:
            return {}
        user = obj.user
        return {
            "id": user.id,
            "username": user.username,
            "avatar": user.avatar
        }
