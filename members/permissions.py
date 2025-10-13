from rest_framework import permissions
from users.models import UserRole

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.has_role(UserRole.ADMIN)

class IsSecretariate(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.has_role(UserRole.SECRETARIATE)

class IsContentManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.has_role(UserRole.CONTENT_MANAGER)

class IsRegularUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.has_role(UserRole.USER)

class IsAuthenticatedAndActive(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.is_active
