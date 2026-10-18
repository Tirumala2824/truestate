from dataclasses import dataclass
from fastapi import HTTPException, Request
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleRequest


@dataclass
class Principal:
    email: str
    reviewer: bool = False
    read_only: bool = False


def user(request: Request):
    s = request.app.state.config
    if s.public_demo:
        from .sandbox import current_store
        if current_store.get() is None:
            raise HTTPException(401, 'Open the workspace to start your sandbox.')
        return Principal(email='Sandbox visitor')
    token = request.headers.get('x-goog-iap-jwt-assertion', '')
    if s.mode != 'app' or not s.iap_audience or not token:
        raise HTTPException(401, 'Sign in through the configured Google IAP application.')
    try:
        claims = id_token.verify_token(token, GoogleRequest(), audience=s.iap_audience,
            certs_url='https://www.gstatic.com/iap/verify/public_key')
        if claims.get('iss') != 'https://cloud.google.com/iap' or not claims.get('sub') or not claims.get('email'):
            raise ValueError('Invalid IAP claims')
    except Exception:
        raise HTTPException(401, 'Google IAP identity could not be verified.')
    email = claims['email'].lower()
    return Principal(email=email, reviewer=email in s.reviewers)


def service(request: Request, connectors=False):
    s = request.app.state.config
    token = request.headers.get('authorization', '').removeprefix('Bearer ')
    allowed = s.source_connectors if connectors else [s.worker_caller]
    if s.mode != 'worker' or not s.worker_audience or not token:
        raise HTTPException(401, 'A Google service identity is required.')
    try:
        claims = id_token.verify_oauth2_token(token, GoogleRequest(), audience=s.worker_audience)
        email = claims.get('email', '').lower()
        if not claims.get('email_verified') or email not in allowed:
            raise ValueError('Service account not allowed')
    except Exception:
        raise HTTPException(403, 'Service identity is not authorized for this endpoint.')
    return email


def reviewer(principal):
    if not principal.reviewer:
        raise HTTPException(403, 'A configured reviewer is required.')
