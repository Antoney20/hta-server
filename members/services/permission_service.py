# """Separated permission service for better organization"""
# from django.contrib.auth import get_user_model
# from ..models import Channel, ChannelMembership
# User = get_user_model()

# class ForumPermissionService:
#     """Handles all forum permission logic"""
    
#     @staticmethod
#     def can_view_channel(user: User, channel: Channel) -> bool:
#         """Check if user can view a channel"""
#         if not channel.is_private:
#             return True
#         return ChannelMembership.objects.filter(channel=channel, user=user).exists()
    
#     @staticmethod
#     def can_manage_members(user: User, channel: Channel) -> bool:
#         """Check if user can add/remove members"""
#         return ChannelMembership.objects.filter(
#             channel=channel, 
#             user=user, 
#             role__in=['owner', 'moderator']
#         ).exists()
    
#     @staticmethod
#     def can_update_channel(user: User, channel: Channel) -> bool:
#         """Check if user can update channel details"""
#         return ChannelMembership.objects.filter(
#             channel=channel, 
#             user=user, 
#             role='owner'
#         ).exists()
    
#     @staticmethod
#     def can_delete_channel(user: User, channel: Channel) -> bool:
#         """Check if user can delete channel"""
#         return ChannelMembership.objects.filter(
#             channel=channel, 
#             user=user, 
#             role='owner'
#         ).exists()
    
#     @staticmethod
#     def is_channel_member(user: User, channel: Channel) -> bool:
#         """Check if user is a channel member"""
#         return ChannelMembership.objects.filter(channel=channel, user=user).exists()
    
#     @staticmethod
#     def get_user_role(user: User, channel: Channel) -> str:
#         """Get user's role in a channel"""
#         try:
#             membership = ChannelMembership.objects.get(channel=channel, user=user)
#             return membership.role
#         except ChannelMembership.DoesNotExist:
#             return None