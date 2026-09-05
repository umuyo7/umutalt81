from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from .models import User
from .pos_models import LoginSession


SESSION_TTL_HOURS = max(1, min(int(os.getenv("SESSION_TTL_HOURS", "12")), 168))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_session(request: Request, db: Session, user: User) -> LoginSession:
    token = secrets.token_urlsafe(48)
    now = datetime.utcnow()
    row = LoginSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=_token_hash(token),
        ip_address=request.client.host[:64] if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:512] or None,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
    )
    db.add(row)
    request.session["login_session_id"] = row.id
    request.session["login_session_token"] = token
    return row


def authenticated_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get("user_id")
    session_id = request.session.get("login_session_id")
    token = request.session.get("login_session_token")
    if not user_id or not session_id or not token:
        return None
    row = db.get(LoginSession, session_id)
    now = datetime.utcnow()
    if (
        row is None
        or row.user_id != user_id
        or row.revoked_at is not None
        or row.expires_at <= now
        or not hmac.compare_digest(row.token_hash, _token_hash(token))
    ):
        request.session.clear()
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        request.session.clear()
        return None
    return user


def revoke_login_session(request: Request, db: Session) -> None:
    session_id = request.session.get("login_session_id")
    if session_id:
        row = db.get(LoginSession, session_id)
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.utcnow()
    request.session.clear()
