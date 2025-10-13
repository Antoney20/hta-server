# """Custom validators"""

# from django.core.exceptions import ValidationError
# from django.utils.translation import gettext_lazy as _
# import re


# class ForumValidators:
#     """Collection of forum-related validators"""
    
#     @staticmethod
#     def validate_channel_name(name: str):
#         """Validate channel name format"""
#         if not re.match(r'^[a-zA-Z0-9_-]+$', name):
#             raise ValidationError(
#                 _('Channel name can only contain letters, numbers, underscores, and hyphens.')
#             )
        
#         if len(name) < 3:
#             raise ValidationError(_('Channel name must be at least 3 characters long.'))
        
#         if len(name) > 50:
#             raise ValidationError(_('Channel name cannot exceed 50 characters.'))
    
#     @staticmethod
#     def validate_message_content(content: str):
#         """Validate message content"""
#         if not content or not content.strip():
#             raise ValidationError(_('Message content cannot be empty.'))
        
#         if len(content) > 2000:
#             raise ValidationError(_('Message cannot exceed 2000 characters.'))
    
#     @staticmethod
#     def validate_user_role(role: str):
#         """Validate user role"""
#         valid_roles = ['owner', 'moderator', 'member']
#         if role not in valid_roles:
#             raise ValidationError(f'Role must be one of: {", ".join(valid_roles)}')
