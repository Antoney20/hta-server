# """Real-time notification service"""

# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync
# from django.contrib.auth import get_user_model

# from ..models import Channel
# from ..serializers import UserSerializer

# User = get_user_model() 

# class ForumNotificationService:
#     """Handles real-time notifications"""
    
#     @staticmethod
#     def notify_member_added(channel: Channel, new_member: User, added_by: User):
#         """Notify channel members when someone is added"""
#         channel_layer = get_channel_layer()
        
#         notification_data = {
#             "type": "member.added",
#             "channel_id": channel.id,
#             "new_member": UserSerializer(new_member).data,
#             "added_by": UserSerializer(added_by).data,
#         }
        
#         async_to_sync(channel_layer.group_send)(
#             f"forum_{channel.id}",
#             {
#                 "type": "member.notification",
#                 "notification": notification_data
#             }
#         )
    
#     @staticmethod
#     def notify_member_removed(channel: Channel, removed_member: User, removed_by: User):
#         """Notify when a member is removed"""
#         channel_layer = get_channel_layer()
        
#         notification_data = {
#             "type": "member.removed",
#             "channel_id": channel.id,
#             "removed_member": UserSerializer(removed_member).data,
#             "removed_by": UserSerializer(removed_by).data,
#         }
        
#         async_to_sync(channel_layer.group_send)(
#             f"forum_{channel.id}",
#             {
#                 "type": "member.notification",
#                 "notification": notification_data
#             }
#         )
    
#     @staticmethod
#     def notify_user_typing(channel: Channel, user: User):
#         """Notify when a user is typing"""
#         channel_layer = get_channel_layer()
        
#         async_to_sync(channel_layer.group_send)(
#             f"forum_{channel.id}",
#             {
#                 "type": "user.typing",
#                 "user": UserSerializer(user).data
#             }
#         )
    
#     @staticmethod
#     def notify_channel_updated(channel: Channel, updated_by: User):
#         """Notify when channel details are updated"""
#         channel_layer = get_channel_layer()
        
#         from ..serializers import ChannelSerializer
        
#         async_to_sync(channel_layer.group_send)(
#             f"forum_{channel.id}",
#             {
#                 "type": "channel.updated",
#                 "channel": ChannelSerializer(channel).data,
#                 "updated_by": UserSerializer(updated_by).data
#             }
#         )