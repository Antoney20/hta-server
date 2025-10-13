# from urllib.parse import parse_qs
# from channels.db import database_sync_to_async
# from django.contrib.auth.models import AnonymousUser
# from rest_framework_simplejwt.tokens import AccessToken

# from users.models import CustomUser


# @database_sync_to_async
# def get_user_from_token(token):
#     try:
#         access = AccessToken(token)
#         user = CustomUser.objects.get(id=access["user_id"])
#         return user
#     except Exception:
#         return AnonymousUser()

# class JWTAuthMiddleware:
#     def __init__(self, inner):
#         self.inner = inner

#     def __call__(self, scope):
#         return JWTAuthMiddlewareInstance(scope, self.inner)

# class JWTAuthMiddlewareInstance:
#     def __init__(self, scope, inner):
#         self.scope = dict(scope)
#         self.inner = inner

#     async def __call__(self, receive, send):
#         query_string = self.scope.get("query_string", b"").decode()
#         params = parse_qs(query_string)
#         token = params.get("token", [None])[0]

#         self.scope["user"] = await get_user_from_token(token)
#         inner = self.inner(self.scope)
#         return await inner(receive, send)
import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken
from channels.db import database_sync_to_async

User = get_user_model()

class JWTAuthMiddleware:
    """
    Custom JWT middleware for Django Channels (ASGI compatible).
    """

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        # Default to anonymous user
        scope["user"] = None

        # Extract token from query string
        query_string = scope.get("query_string", b"").decode()
        token = None
        if query_string and "token=" in query_string:
            token = query_string.split("token=")[-1]

        if token:
            try:
                access = AccessToken(token)
                user = await self.get_user(access["user_id"])
                scope["user"] = user
            except Exception:
                scope["user"] = None

        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

