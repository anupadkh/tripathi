import hashlib
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.extensions import OpenApiAuthenticationExtension
from .models import AccessToken


class ExpiringTokenAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header or header[0].lower() != b"bearer":
            return None
        if len(header) != 2:
            raise AuthenticationFailed("Invalid authorization header.")
        digest = hashlib.sha256(header[1]).hexdigest()
        token = (
            AccessToken.objects.select_related("user")
            .filter(digest=digest, expires_at__gt=timezone.now(), user__is_active=True)
            .first()
        )
        if not token:
            raise AuthenticationFailed("Token expired or revoked. Sign in again.")
        return token.user, token

    def authenticate_header(self, request):
        return "Bearer"


class TokenSchema(OpenApiAuthenticationExtension):
    target_class = "operations.authentication.ExpiringTokenAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {"type": "http", "scheme": "bearer"}
