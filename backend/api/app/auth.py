from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from http import HTTPStatus
from threading import RLock
from typing import Protocol, cast
from uuid import UUID, uuid5

import httpx
from fastapi import Request

from .errors import CarePathError

ACCOUNT_NAMESPACE = UUID("9f8788ea-7d7c-4bdc-99a5-8e1bf17e670e")


@dataclass(frozen=True)
class AuthIdentity:
    subject: str
    email: str | None


class AuthVerifier(Protocol):
    def verify(self, access_token: str) -> AuthIdentity: ...


class AuthTokenInvalidError(ValueError):
    pass


class AuthServiceUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class _CachedIdentity:
    identity: AuthIdentity
    expires_at: datetime


class SupabaseAuthVerifier:
    """Verify Supabase access tokens without storing raw tokens."""

    def __init__(
        self,
        *,
        supabase_url: str,
        publishable_key: str,
        timeout_seconds: float = 5.0,
        cache_minutes: int = 5,
    ) -> None:
        self._user_url = f"{supabase_url.rstrip('/')}/auth/v1/user"
        self._publishable_key = publishable_key
        self._timeout_seconds = timeout_seconds
        self._cache_ttl = timedelta(minutes=cache_minutes)
        self._cache: dict[str, _CachedIdentity] = {}
        self._lock = RLock()

    def verify(self, access_token: str) -> AuthIdentity:
        digest = sha256(access_token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        with self._lock:
            cached = self._cache.get(digest)
            if cached is not None and cached.expires_at > now:
                return cached.identity
            self._cache.pop(digest, None)

        try:
            response = httpx.get(
                self._user_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": self._publishable_key,
                    "Accept": "application/json",
                },
                timeout=self._timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AuthServiceUnavailableError("Supabase Auth could not be reached") from exc

        if response.status_code in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
            raise AuthTokenInvalidError("The Supabase access token is invalid or expired")
        if response.status_code != HTTPStatus.OK:
            raise AuthServiceUnavailableError(
                f"Supabase Auth returned status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthServiceUnavailableError("Supabase Auth returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise AuthServiceUnavailableError("Supabase Auth returned an invalid user payload")
        subject = payload.get("id")
        email = payload.get("email")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthServiceUnavailableError("Supabase Auth user payload is missing an id")
        identity = AuthIdentity(
            subject=subject.strip(),
            email=email.strip() if isinstance(email, str) and email.strip() else None,
        )
        with self._lock:
            self._cache[digest] = _CachedIdentity(
                identity=identity,
                expires_at=now + self._cache_ttl,
            )
        return identity


def carepath_account_user_id(subject: str) -> UUID:
    return uuid5(ACCOUNT_NAMESPACE, f"supabase:{subject}")


def get_optional_auth_identity(request: Request) -> AuthIdentity | None:
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token.strip():
        raise CarePathError(
            "invalid_authorization_header",
            "Authorization must use a Bearer token",
            status_code=HTTPStatus.UNAUTHORIZED,
        )

    verifier = cast(AuthVerifier | None, getattr(request.app.state, "auth_verifier", None))
    if verifier is None:
        raise CarePathError(
            "auth_not_configured",
            "Account sign-in is not configured for this deployment",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        )
    try:
        return verifier.verify(token.strip())
    except AuthTokenInvalidError as exc:
        raise CarePathError(
            "invalid_access_token",
            "The account session is invalid or expired",
            status_code=HTTPStatus.UNAUTHORIZED,
        ) from exc
    except AuthServiceUnavailableError as exc:
        raise CarePathError(
            "auth_service_unavailable",
            "Account verification is temporarily unavailable",
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        ) from exc


def require_auth_identity(request: Request) -> AuthIdentity:
    identity = get_optional_auth_identity(request)
    if identity is None:
        raise CarePathError(
            "authentication_required",
            "Sign in is required for this account operation",
            status_code=HTTPStatus.UNAUTHORIZED,
        )
    return identity
