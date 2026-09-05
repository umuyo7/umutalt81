from __future__ import annotations

from contextvars import ContextVar, Token

from fastapi import Request


_context: ContextVar[dict] = ContextVar("bereket_request_context", default={})


def begin_request(request_id: str, request: Request) -> Token:
    return _context.set({
        "request_id": request_id,
        "ip_address": request.client.host[:64] if request.client else None,
        "user_agent": (request.headers.get("user-agent") or "")[:512] or None,
        "session_id": None,
    })


def bind_session(session_id: str | None) -> None:
    # Sync FastAPI dependency'leri thread pool'da çalışır; kopyalanmış context içindeki
    # aynı request-scope sözlüğünü yerinde güncellemek ana handler ile bilgiyi paylaşır.
    current = _context.get()
    current["session_id"] = session_id


def current_request_context() -> dict:
    return _context.get()


def end_request(token: Token) -> None:
    _context.reset(token)
