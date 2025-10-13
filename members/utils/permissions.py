# # """Custom permission classes"""

# # from rest_framework import permissions
# # from ..services import ForumPermissionService


# # class IsChannelMember(permissions.BasePermission):
# #     """Permission to check if user is a channel member"""
    
# #     def has_object_permission(self, request, view, obj):
# #         return ForumPermissionService.is_channel_member(request.user, obj)


# # class IsChannelOwnerOrModerator(permissions.BasePermission):
# #     """Permission to check if user is channel owner or moderator"""
    
# #     def has_object_permission(self, request, view, obj):
# #         return ForumPermissionService.can_manage_members(request.user, obj)


# # class IsChannelOwner(permissions.BasePermission):
# #     """Permission to check if user is channel owner"""
    
# #     def has_object_permission(self, request, view, obj):
# #         return ForumPermissionService.can_update_channel(request.user, obj)
# """
# Custom permission classes for forum functionality
# """
# from rest_framework import permissions
# from ..services.permission_service import ForumPermissionService


# class IsChannelMember(permissions.BasePermission):
#     """Permission to check if user is a channel member"""
    
#     message = "You must be a member of this channel."
    
#     def has_object_permission(self, request, view, obj):
#         if not request.user or not request.user.is_authenticated:
#             return False
#         return ForumPermissionService.is_channel_member(request.user, obj)


# class IsChannelOwnerOrModerator(permissions.BasePermission):
#     """Permission to check if user is channel owner or moderator"""
    
#     message = "Only channel owners or moderators can perform this action."
    
#     def has_object_permission(self, request, view, obj):
#         if not request.user or not request.user.is_authenticated:
#             return False
#         return ForumPermissionService.can_manage_members(request.user, obj)


# class IsChannelOwner(permissions.BasePermission):
#     """Permission to check if user is channel owner"""
    
#     message = "Only channel owners can perform this action."
    
#     def has_object_permission(self, request, view, obj):
#         if not request.user or not request.user.is_authenticated:
#             return False
#         return ForumPermissionService.can_update_channel(request.user, obj)


# class IsMessageOwnerOrModerator(permissions.BasePermission):
#     """Permission to check if user owns the message or is a channel moderator"""
    
#     message = "You can only modify your own messages, or you must be a channel moderator."
    
#     def has_object_permission(self, request, view, obj):
#         if not request.user or not request.user.is_authenticated:
#             return False
        
#         # Message owner can always edit/delete their own messages
#         if obj.user == request.user:
#             return True
        
#         # Channel moderators and owners can manage messages
#         return ForumPermissionService.can_manage_members(request.user, obj.channel)


# # Alias for backward compatibility
# ForumPermissions = {
#     'IsChannelMember': IsChannelMember,
#     'IsChannelOwnerOrModerator': IsChannelOwnerOrModerator,
#     'IsChannelOwner': IsChannelOwner,
#     'IsMessageOwnerOrModerator': IsMessageOwnerOrModerator,
# }
