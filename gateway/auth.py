"""OAuth 2.1 authorization server (client-credentials grant) built on Authlib.

Authlib ships no FastAPI provider integration, so this module subclasses the
framework-agnostic base classes and adapts Starlette requests itself.

Phase 0: one in-memory client, opaque bearer tokens, single scope ``mcp:tools``.
Production upgrades (roadmap Phase 2): persistent client store, JWT access
tokens, authorization-code + PKCE flow for user login.
"""
import hmac
import os
import time

from authlib.common.security import generate_token as _random_token
from authlib.oauth2 import AuthorizationServer as BaseAuthorizationServer
from authlib.oauth2 import ResourceProtector as BaseResourceProtector
from authlib.oauth2.rfc6749 import grants
from authlib.oauth2.rfc6749.errors import OAuth2Error
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload, OAuth2Request
from authlib.oauth2.rfc6750 import BearerTokenGenerator, BearerTokenValidator
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse, Response

# Local dev runs over plain http; Authlib refuses that unless this is set.
# Production MUST serve https and unset it.
os.environ.setdefault("AUTHLIB_INSECURE_TRANSPORT", "1")

TOKEN_TTL = int(os.environ.get("GATEWAY_TOKEN_TTL", "3600"))
CLIENT_ID = os.environ.get("GATEWAY_CLIENT_ID", "demo-client")
CLIENT_SECRET = os.environ.get("GATEWAY_CLIENT_SECRET", "demo-secret")
SCOPE = "mcp:tools"

_CLIENTS = {
    CLIENT_ID: {"client_secret": CLIENT_SECRET, "scope": SCOPE},
}


class Token:
    """Opaque access token kept in memory (Phase 0)."""

    def __init__(self, access_token, client_id, scope, expires_at):
        self.access_token = access_token
        self.client_id = client_id
        self._scope = scope
        self.expires_at = expires_at

    def get_scope(self):
        return self._scope

    def is_expired(self, leeway=0):
        return time.time() > self.expires_at - leeway

    def is_revoked(self):
        return False


TOKENS: dict[str, Token] = {}


class Client:
    """Minimal OAuth2 client record for Authlib's ClientCredentialsGrant."""

    def __init__(self, client_id, client_secret, scope):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope

    def check_client_secret(self, secret):
        return hmac.compare_digest(secret or "", self.client_secret)

    def check_endpoint_auth_method(self, method, endpoint):
        return method in ("client_secret_post", "client_secret_basic")

    def check_grant_type(self, grant_type):
        return grant_type == "client_credentials"

    def check_response_type(self, response_type):
        return False

    def get_allowed_scope(self, scope):
        if not scope:
            return self.scope
        allowed = set(self.scope.split())
        return scope if set(scope.split()) <= allowed else ""

    def check_redirect_uri(self, uri):
        return True


def query_client(client_id):
    record = _CLIENTS.get(client_id)
    if not record:
        return None
    return Client(client_id, record["client_secret"], record["scope"])


def save_token(token, request):
    tok = Token(
        access_token=token["access_token"],
        client_id=request.client.client_id,
        scope=token.get("scope", SCOPE),
        expires_at=int(time.time()) + int(token.get("expires_in", TOKEN_TTL)),
    )
    TOKENS[tok.access_token] = tok


class StarletteOAuth2Request(OAuth2Request):
    """OAuth2Request adapted from a Starlette request + parsed form body.

    Authlib's ``client_secret_post`` authenticator reads ``request.form``,
    which only the Flask/Django request wrappers provide — hence this class.
    """

    def __init__(self, method, uri, headers, form):
        super().__init__(method=method, uri=uri, headers=headers)
        self.payload = BasicOAuth2Payload(form)
        self._form = form

    @property
    def form(self):
        return self._form


def _access_token_generator(client=None, grant_type=None, user=None, scope=None):
    # Authlib's BearerTokenGenerator calls this with client/grant kwargs;
    # the plain generate_token() helper takes only a length.
    return _random_token(42)


def build_oauth2_request(request: Request, form: dict) -> OAuth2Request:
    """Adapt a Starlette request + parsed form body to Authlib's request."""
    return StarletteOAuth2Request(
        method=request.method,
        uri=str(request.url),
        headers=dict(request.headers),
        form=form,
    )


class ClientCredentialsGrant(grants.ClientCredentialsGrant):
    """client_credentials grant that also accepts credentials in the form body.

    Authlib's default only tries ``client_secret_basic``; curl and most
    simple clients post ``client_id``/``client_secret`` as form fields.
    """

    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post"]


class GatewayAuthorizationServer(BaseAuthorizationServer):
    def __init__(self, query_client_fn, save_token_fn):
        super().__init__(scopes_supported=[SCOPE])
        self._query_client = query_client_fn
        self._save_token = save_token_fn
        self.register_token_generator(
            "default",
            BearerTokenGenerator(_access_token_generator, None, TOKEN_TTL),
        )

    def query_client(self, client_id):
        return self._query_client(client_id)

    def save_token(self, token, request):
        return self._save_token(token, request)

    def create_oauth2_request(self, request):
        # The endpoint already built an OAuth2Request; pass it through.
        return request

    def send_signal(self, name, *args, **kwargs):
        # No signal system in Phase 0; the base raises NotImplementedError.
        return None

    def handle_response(self, status, body, headers):
        # Authlib returns headers as a list of tuples; Starlette wants a dict.
        headers = dict(headers) if headers else {}
        if isinstance(body, dict):
            return JSONResponse(content=body, status_code=status, headers=headers)
        return Response(content=body, status_code=status, headers=headers)


server = GatewayAuthorizationServer(query_client, save_token)
server.register_grant(ClientCredentialsGrant)


class GatewayTokenValidator(BearerTokenValidator):
    def authenticate_token(self, token_string):
        return TOKENS.get(token_string)


protector = BaseResourceProtector()
protector.register_token_validator(GatewayTokenValidator())


async def require_token(request: Request) -> Token:
    """FastAPI dependency: valid Bearer token with scope ``mcp:tools`` or 401."""
    try:
        return protector.validate_request([SCOPE], request)
    except OAuth2Error as exc:
        headers = {
            "WWW-Authenticate": f'Bearer realm="mcp-gateway", error="{exc.error}"'
        }
        raise HTTPException(
            status_code=getattr(exc, "status_code", 401),
            detail=exc.description or exc.error,
            headers=headers,
        )
