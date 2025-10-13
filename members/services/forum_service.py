# # services/forum_service.py
# """Main forum service combining channel and message operations"""

# from django.db import transaction

# from typing import Dict, List, Optional

# from ..models import Channel, ChannelMembership, Message
# from ..serializers import ChannelSerializer, ChannelMembershipSerializer, MessageSerializer
# from .permission_service import ForumPermissionService
# from .notification_service import ForumNotificationService
# from .websocket_service import WebSocketService
# from django.contrib.auth import get_user_model
# from ..models import Channel, ChannelMembership
# User = get_user_model()

# class ForumChannelService:
#     """Handles channel-related business logic"""
    
#     @staticmethod
#     def create_channel(user: User, channel_data: Dict) -> Channel:
#         """Create a new channel and add creator as owner"""
#         with transaction.atomic():
#             serializer = ChannelSerializer(data=channel_data)
#             if serializer.is_valid(raise_exception=True):
#                 channel = serializer.save(created_by=user)
                
#                 # Add creator as owner
#                 ChannelMembership.objects.create(
#                     channel=channel,
#                     user=user,
#                     role='owner'
#                 )
                
#                 return channel
    
#     @staticmethod
#     def get_user_channels(user: User):
#         """Get all channels accessible to user"""
#         from django.db.models import Q
#         return Channel.objects.filter(
#             Q(is_private=False) | 
#             Q(is_private=True, memberships__user=user)
#         ).distinct()
    
#     @staticmethod
#     def add_member(channel: Channel, user_id: int, role: str = 'member', added_by: User = None) -> ChannelMembership:
#         """Add a member to channel with real-time notification"""
#         user = User.objects.get(id=user_id)
        
#         # Check if user is already a member
#         if ChannelMembership.objects.filter(channel=channel, user=user).exists():
#             raise ValueError("User is already a member of this channel")
        
#         membership_data = {
#             'channel': channel.id,
#             'user_id': user_id,
#             'role': role
#         }
        
#         serializer = ChannelMembershipSerializer(data=membership_data)
#         if serializer.is_valid(raise_exception=True):
#             membership = serializer.save()
            
#             # Send real-time notification if added_by is provided
#             if added_by:
#                 ForumNotificationService.notify_member_added(channel, user, added_by)
            
#             return membership
    
#     @staticmethod
#     def remove_member(channel: Channel, user_id: int, removed_by: User) -> bool:
#         """Remove a member from channel"""
#         try:
#             user = User.objects.get(id=user_id)
#             membership = ChannelMembership.objects.get(channel=channel, user=user)
            
#             # Don't allow removing the last owner
#             if membership.role == 'owner':
#                 owner_count = ChannelMembership.objects.filter(
#                     channel=channel, 
#                     role='owner'
#                 ).count()
#                 if owner_count <= 1:
#                     raise ValueError("Cannot remove the last owner of the channel")
            
#             membership.delete()
            
#             # Send notification
#             ForumNotificationService.notify_member_removed(channel, user, removed_by)
            
#             return True
#         except (User.DoesNotExist, ChannelMembership.DoesNotExist):
#             return False
    
#     @staticmethod
#     def update_member_role(channel: Channel, user_id: int, new_role: str, updated_by: User) -> ChannelMembership:
#         """Update a member's role"""
#         user = User.objects.get(id=user_id)
#         membership = ChannelMembership.objects.get(channel=channel, user=user)
        
#         old_role = membership.role
#         membership.role = new_role
#         membership.save()
        
#         # Send notification about role change
#         ForumNotificationService.notify_member_role_changed(
#             channel, user, old_role, new_role, updated_by
#         )
        
#         return membership
    
#     @staticmethod
#     def get_channel_members(channel: Channel) -> List[ChannelMembership]:
#         """Get all members of a channel"""
#         return ChannelMembership.objects.filter(channel=channel).select_related('user')
    
#     @staticmethod
#     def update_channel(channel: Channel, update_data: Dict, updated_by: User) -> Channel:
#         """Update channel details"""
#         serializer = ChannelSerializer(channel, data=update_data, partial=True)
#         if serializer.is_valid(raise_exception=True):
#             updated_channel = serializer.save()
            
#             # Notify members about channel update
#             ForumNotificationService.notify_channel_updated(updated_channel, updated_by)
            
#             return updated_channel


# class ForumMessageService:
#     """Handles message-related business logic with WebSocket broadcasting"""
    
#     @staticmethod
#     def send_message(channel: Channel, user: User, content: str) -> Message:
#         """Send a message and broadcast to all channel members"""
#         # Validate message content
#         from ..utils.validators import ForumValidators
#         ForumValidators.validate_message_content(content)
        
#         message_data = {
#             'channel': channel.id,
#             'user_id': user.id,
#             'content': content.strip()
#         }
        
#         serializer = MessageSerializer(data=message_data)
#         if serializer.is_valid(raise_exception=True):
#             message = serializer.save()
            
#             # Broadcast message to all channel members via WebSocket
#             ForumMessageService._broadcast_message(channel, message)
            
#             return message
    
#     @staticmethod
#     def _broadcast_message(channel: Channel, message: Message):
#         """Broadcast message to all channel members via WebSocket"""
#         # Serialize message for broadcasting
#         message_data = MessageSerializer(message).data
        
#         # Use WebSocket service to broadcast
#         WebSocketService.broadcast_message(str(channel.id), message_data)
    
#     @staticmethod
#     def get_channel_messages(channel: Channel, limit: int = 50, offset: int = 0):
#         """Get recent messages from a channel with pagination"""
#         return Message.objects.filter(channel=channel).select_related('user').order_by('-created_at')[offset:offset+limit]
    
#     @staticmethod
#     def delete_message(message: Message, deleted_by: User) -> bool:
#         """Delete a message (if user has permission)"""
#         # Check if user can delete this message
#         if message.user != deleted_by:
#             # Check if user is moderator or owner
#             if not ForumPermissionService.can_manage_members(deleted_by, message.channel):
#                 raise PermissionError("You don't have permission to delete this message")
        
#         message_id = message.id
#         channel_id = str(message.channel.id)
#         message.delete()
        
#         # Broadcast message deletion
#         WebSocketService.send_to_channel_group(
#             channel_id,
#             "message.deleted",
#             {
#                 "message_id": message_id,
#                 "deleted_by": {
#                     "id": deleted_by.id,
#                     "username": deleted_by.username
#                 }
#             }
#         )
        
#         return True
    
#     @staticmethod
#     def edit_message(message: Message, new_content: str, edited_by: User) -> Message:
#         """Edit a message (if user has permission)"""
#         # Only allow the original sender to edit
#         if message.user != edited_by:
#             raise PermissionError("You can only edit your own messages")
        
#         # Validate new content
#         from ..utils.validators import ForumValidators
#         ForumValidators.validate_message_content(new_content)
        
#         old_content = message.content
#         message.content = new_content.strip()
#         message.is_edited = True
#         message.save()
        
#         # Broadcast message edit
#         message_data = MessageSerializer(message).data
#         WebSocketService.send_to_channel_group(
#             str(message.channel.id),
#             "message.edited",
#             {
#                 "message": message_data,
#                 "old_content": old_content
#             }
#         )
        
#         return message


# class ForumSearchService:
#     """Handles search functionality"""
    
#     @staticmethod
#     def search_channels(user: User, query: str, include_private: bool = True):
#         """Search for channels accessible to the user"""
#         from django.db.models import Q
        
#         base_query = Q(name__icontains=query) | Q(description__icontains=query)
        
#         if include_private:
#             # Include private channels where user is a member
#             channel_filter = (
#                 Q(is_private=False) | 
#                 Q(is_private=True, memberships__user=user)
#             )
#         else:
#             # Only public channels
#             channel_filter = Q(is_private=False)
        
#         return Channel.objects.filter(base_query & channel_filter).distinct()
    
#     @staticmethod
#     def search_messages(user: User, channel: Channel, query: str, limit: int = 20):
#         """Search for messages in a channel"""
#         # Check if user can access the channel
#         if not ForumPermissionService.can_view_channel(user, channel):
#             raise PermissionError("You don't have access to this channel")
        
#         from django.db.models import Q
        
#         return Message.objects.filter(
#             channel=channel,
#             content__icontains=query
#         ).select_related('user').order_by('-created_at')[:limit]


# class ForumStatsService:
#     """Handles forum statistics"""
    
#     @staticmethod
#     def get_channel_stats(channel: Channel) -> Dict:
#         """Get statistics for a channel"""
#         member_count = ChannelMembership.objects.filter(channel=channel).count()
#         message_count = Message.objects.filter(channel=channel).count()
        
#         # Get most active members
#         from django.db.models import Count
#         active_members = (
#             Message.objects.filter(channel=channel)
#             .values('user__username', 'user__first_name', 'user__last_name')
#             .annotate(message_count=Count('id'))
#             .order_by('-message_count')[:5]
#         )
        
#         return {
#             'member_count': member_count,
#             'message_count': message_count,
#             'active_members': active_members,
#             'created_at': channel.created_at,
#             'is_private': channel.is_private
#         }
    
#     @staticmethod
#     def get_user_stats(user: User) -> Dict:
#         """Get statistics for a user"""
#         channels_count = ChannelMembership.objects.filter(user=user).count()
#         messages_count = Message.objects.filter(user=user).count()
#         owned_channels = ChannelMembership.objects.filter(user=user, role='owner').count()
        
#         return {
#             'channels_joined': channels_count,
#             'messages_sent': messages_count,
#             'channels_owned': owned_channels
#         }