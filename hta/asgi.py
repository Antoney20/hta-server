"""
ASGI config for hta project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hta.settings')

application = get_asgi_application()

# """
# ASGI config for hta project with WebSocket support.
# """

# import os
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# from channels.security.websocket import AllowedHostsOriginValidator
# from django.core.asgi import get_asgi_application

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hta.settings')

# # Initialize Django ASGI application early to ensure the AppRegistry
# # is populated before importing code that may import ORM models.
# django_asgi_app = get_asgi_application()

# # Import routing after Django is set up
# from members.routing import websocket_urlpatterns

# application = ProtocolTypeRouter({
#     "http": django_asgi_app,
#     "websocket": AllowedHostsOriginValidator(
#         AuthMiddlewareStack(
#             URLRouter(websocket_urlpatterns)
#         )
#     ),
# })


# """
# ASGI config for hta project with WebSocket + JWTAuthMiddleware support.
# """

# import os
# import django
# from django.core.asgi import get_asgi_application
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.security.websocket import AllowedHostsOriginValidator

# os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hta.settings")

# # Setup Django first
# django.setup()

# # Standard Django ASGI app
# django_asgi_app = get_asgi_application()

# # Import routing and middleware AFTER Django is setup
# from members.routing import websocket_urlpatterns
# from .middleware import JWTAuthMiddleware  

# application = ProtocolTypeRouter({
#     "http": django_asgi_app,
#     "websocket": AllowedHostsOriginValidator(
#         JWTAuthMiddleware(
#             URLRouter(websocket_urlpatterns)
#         )
#     ),
# })

