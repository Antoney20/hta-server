# """
# WebSocket consumers for real-time forum functionality
# """
# import json
# import logging 
# from channels.generic.websocket import AsyncWebsocketConsumer
# from channels.db import database_sync_to_async
# from django.contrib.auth.models import User
# from .models import Channel
# from .services import ForumPermissionService, ForumMessageService
# from .serializers import MessageSerializer

# logger = logging.getLogger(__name__)


# class ForumConsumer(AsyncWebsocketConsumer):
#     """WebSocket consumer for real-time forum communication"""
    
#     async def connect(self):
#         self.channel_id = self.scope['url_route']['kwargs']['channel_id']
#         self.channel_group_name = f'forum_{self.channel_id}'
#         self.user = self.scope['user']
        
#         # Check authentication
#         if not self.user.is_authenticated:
#             logger.warning(f"Unauthenticated user tried to connect to channel {self.channel_id}")
#             await self.close(code=4001)
#             return
        
#         # Check channel access
#         try:
#             can_access = await self.check_channel_access()
#             if not can_access:
#                 logger.warning(f"User {self.user.username} denied access to channel {self.channel_id}")
#                 await self.close(code=4003)
#                 return
#         except Exception as e:
#             logger.error(f"Error checking channel access: {e}")
#             await self.close(code=4000)
#             return
        
#         # Join channel group
#         await self.channel_layer.group_add(
#             self.channel_group_name,
#             self.channel_name
#         )
        
#         await self.accept()
        
#         logger.info(f"User {self.user.username} connected to channel {self.channel_id}")
        
#         # Notify others that user joined
#         await self.channel_layer.group_send(
#             self.channel_group_name,
#             {
#                 'type': 'user_joined',
#                 'user': {
#                     'id': self.user.id,
#                     'username': self.user.username,
#                     'first_name': self.user.first_name,
#                     'last_name': self.user.last_name,
#                 }
#             }
#         )
    
#     async def disconnect(self, close_code):
#         if hasattr(self, 'channel_group_name'):
#             await self.channel_layer.group_discard(
#                 self.channel_group_name,
#                 self.channel_name
#             )
            
#             if hasattr(self, 'user') and self.user.is_authenticated:
#                 await self.channel_layer.group_send(
#                     self.channel_group_name,
#                     {
#                         'type': 'user_left',
#                         'user': {
#                             'id': self.user.id,
#                             'username': self.user.username,
#                         }
#                     }
#                 )
        
#         logger.info(f"User {getattr(self.user, 'username', 'Unknown')} disconnected from channel {self.channel_id}")
    
#     async def receive(self, text_data):
#         """Handle incoming WebSocket messages"""
#         try:
#             data = json.loads(text_data)
#             message_type = data.get('type')
            
#             logger.debug(f"Received message type: {message_type} from user: {self.user.username}")
            
#             if message_type == 'chat.message':
#                 await self.handle_chat_message(data)
#             elif message_type == 'user.typing':
#                 await self.handle_typing_indicator(data)
#             elif message_type == 'user.stop_typing':
#                 await self.handle_stop_typing(data)
#             else:
#                 logger.warning(f"Unknown message type: {message_type}")
                
#         except json.JSONDecodeError as e:
#             logger.error(f"Invalid JSON received: {e}")
#             await self.send(text_data=json.dumps({'error': 'Invalid JSON format'}))
#         except Exception as e:
#             logger.error(f"Error processing message: {e}")
#             await self.send(text_data=json.dumps({'error': 'Internal server error'}))
    
#     async def handle_chat_message(self, data):
#         """Handle chat message sending"""
#         content = data.get('content', '').strip()
#         if not content:
#             await self.send(text_data=json.dumps({'error': 'Message content cannot be empty'}))
#             return
        
#         try:
#             # Save message
#             message = await self.save_message(content)
#             if message:
#                 # ✅ Serialize for broadcast
#                 serializer = MessageSerializer(message)
#                 serialized_message = serializer.data

#                 await self.channel_layer.group_send(
#                     self.channel_group_name,
#                     {
#                         'type': 'chat_message',
#                         'message': serialized_message,  # safe dict
#                     }
#                 )
#                 logger.info(f"Message broadcasted in channel {self.channel_id}")
#             else:
#                 await self.send(text_data=json.dumps({'error': 'Failed to save message'}))
#         except Exception as e:
#             logger.error(f"Error saving message: {e}")
#             await self.send(text_data=json.dumps({'error': 'Failed to send message'}))
    
#     async def handle_typing_indicator(self, data):
#         await self.channel_layer.group_send(
#             self.channel_group_name,
#             {
#                 'type': 'user_typing',
#                 'user': {'id': self.user.id, 'username': self.user.username}
#             }
#         )
    
#     async def handle_stop_typing(self, data):
#         await self.channel_layer.group_send(
#             self.channel_group_name,
#             {
#                 'type': 'user_stop_typing',
#                 'user': {'id': self.user.id, 'username': self.user.username}
#             }
#         )
    
#     # WebSocket event handlers
#     async def chat_message(self, event):
#         await self.send(text_data=json.dumps({
#             'type': 'chat.message',
#             'message': event['message']  # already serialized
#         }))
    
#     async def user_joined(self, event):
#         if event['user']['id'] != self.user.id:
#             await self.send(text_data=json.dumps({'type': 'user.joined', 'user': event['user']}))
    
#     async def user_left(self, event):
#         if event['user']['id'] != self.user.id:
#             await self.send(text_data=json.dumps({'type': 'user.left', 'user': event['user']}))
    
#     async def user_typing(self, event):
#         if event['user']['id'] != self.user.id:
#             await self.send(text_data=json.dumps({'type': 'user.typing', 'user': event['user']}))
    
#     async def user_stop_typing(self, event):
#         if event['user']['id'] != self.user.id:
#             await self.send(text_data=json.dumps({'type': 'user.stop_typing', 'user': event['user']}))
    
#     async def member_notification(self, event):
#         await self.send(text_data=json.dumps({
#             'type': 'member.notification',
#             'notification': event['notification']
#         }))
    
#     async def channel_updated(self, event):
#         await self.send(text_data=json.dumps({
#             'type': 'channel.updated',
#             'channel': event['channel'],
#             'updated_by': event['updated_by']
#         }))
    
#     # Database operations
#     @database_sync_to_async
#     def check_channel_access(self):
#         try:
#             channel = Channel.objects.get(id=self.channel_id)
#             return ForumPermissionService.can_view_channel(self.user, channel)
#         except Channel.DoesNotExist:
#             return False
#         except Exception as e:
#             logger.error(f"Error checking channel access: {e}")
#             return False
    
#     @database_sync_to_async
#     def save_message(self, content):
#         try:
#             channel = Channel.objects.get(id=self.channel_id)
#             if ForumPermissionService.is_channel_member(self.user, channel):
#                 return ForumMessageService.send_message(channel, self.user, content)
#             else:
#                 logger.warning(f"User {self.user.username} is not a member of channel {self.channel_id}")
#                 return None
#         except Channel.DoesNotExist:
#             logger.error(f"Channel {self.channel_id} does not exist")
#             return None
#         except Exception as e:
#             logger.error(f"Error saving message: {e}")
#             return None


# class PresenceConsumer(AsyncWebsocketConsumer):
#     """Consumer for tracking user presence across the app"""
    
#     async def connect(self):
#         if not self.scope['user'].is_authenticated:
#             await self.close(code=4001)
#             return
        
#         self.user_group = f"user_{self.scope['user'].id}"
        
#         await self.channel_layer.group_add(
#             self.user_group,
#             self.channel_name
#         )
        
#         await self.accept()
#         logger.info(f"User {self.scope['user'].username} connected to presence")
        
#         # Update user status to online
#         await self.update_user_status(True)
    
#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.user_group,
#             self.channel_name
#         )
        
#         # Update user status to offline
#         await self.update_user_status(False)
#         logger.info(f"User {self.scope['user'].username} disconnected from presence")
    
#     @database_sync_to_async
#     def update_user_status(self, is_online):
#         """Update user's online status"""
#         # For now, we'll just log this
#         # You can implement a UserStatus model or use Redis for this
#         logger.info(f"User {self.scope['user'].username} status: {'online' if is_online else 'offline'}")
#         pass