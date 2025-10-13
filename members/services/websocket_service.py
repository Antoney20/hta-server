# """WebSocket utility service"""

# from channels.layers import get_channel_layer
# from asgiref.sync import async_to_sync
# import json


# class WebSocketService:
#     """Utility service for WebSocket operations"""
    
#     @staticmethod
#     def send_to_channel_group(channel_id: str, message_type: str, data: dict):
#         """Send a message to a channel group"""
#         channel_layer = get_channel_layer()
        
#         async_to_sync(channel_layer.group_send)(
#             f"forum_{channel_id}",
#             {
#                 "type": message_type,
#                 **data
#             }
#         )
    
#     @staticmethod
#     def send_to_user(user_id: int, message_type: str, data: dict):
#         """Send a message to a specific user"""
#         channel_layer = get_channel_layer()
        
#         async_to_sync(channel_layer.group_send)(
#             f"user_{user_id}",
#             {
#                 "type": message_type,
#                 **data
#             }
#         )
    
#     @staticmethod
#     def broadcast_message(channel_id: str, message_data: dict):
#         """Broadcast a chat message to all channel members"""
#         WebSocketService.send_to_channel_group(
#             channel_id,
#             "chat.message", 
#             {"message": message_data}
#         )
    
#     @staticmethod
#     def broadcast_user_status(channel_id: str, user_data: dict, status: str):
#         """Broadcast user online/offline status"""
#         WebSocketService.send_to_channel_group(
#             channel_id,
#             f"user.{status}",
#             {"user": user_data}
#         )