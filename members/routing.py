# """
# WebSocket URL routing for the members app
# """
# from django.urls import re_path
# from . import consumers

# websocket_urlpatterns = [
#     re_path(r'^ws/forum/(?P<channel_id>[\w-]+)/$', consumers.ForumConsumer.as_asgi()),
#     re_path(r'^ws/presence/$', consumers.PresenceConsumer.as_asgi()),
# ]