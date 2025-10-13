from rest_framework.exceptions import PermissionDenied
from functools import wraps

def role_required(*roles):
    """
    Decorator to restrict access to users with specified roles.
    Usage: @role_required('admin', 'secretariate')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            user = request.user
            if not user or not user.is_authenticated:
                raise PermissionDenied("Authentication required.")
            if not any(user.has_role(role) for role in roles):
                raise PermissionDenied("You do not have permission to complete this task.")
            return func(self, request, *args, **kwargs)
        return wrapper
    return decorator
