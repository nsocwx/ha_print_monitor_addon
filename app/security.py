"""Signed one-time action token helpers."""
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session, select

from app.core.config import AppConfig
from app.models.event import ActionTokenNonce


class ActionTokenError(Exception):
    """Raised when an action token is invalid, expired, or replayed."""


@dataclass
class ActionTokenClaims:
    """Verified action token claims."""

    event_id: str
    action: str
    printer_id: str
    expires_at: datetime
    nonce: str


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _secret(config: AppConfig) -> bytes:
    return config.security.action_signing_secret.encode("utf-8")


def create_action_token(
    config: AppConfig,
    event_id: str,
    action: str,
    printer_id: str,
    expires_at: Optional[datetime] = None,
) -> str:
    """Create a signed action token for one event/action/printer."""
    expiry = expires_at or (
        datetime.utcnow() + timedelta(hours=config.security.action_token_ttl_hours)
    )
    payload = {
        "event_id": event_id,
        "action": action,
        "printer_id": printer_id,
        "exp": int(expiry.timestamp()),
        "nonce": secrets.token_urlsafe(18),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64encode(payload_bytes)
    signature = hmac.new(_secret(config), payload_part.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def verify_action_token(
    token: str,
    expected_action: str,
    config: AppConfig,
    session: Session,
    mark_used: bool = True,
) -> ActionTokenClaims:
    """Verify and optionally consume a signed one-time action token."""
    try:
        payload_part, signature_part = token.split(".", 1)
        expected_sig = hmac.new(
            _secret(config), payload_part.encode("ascii"), hashlib.sha256
        ).digest()
        provided_sig = _b64decode(signature_part)
        if not hmac.compare_digest(expected_sig, provided_sig):
            raise ActionTokenError("Invalid action token")

        payload = json.loads(_b64decode(payload_part))
        event_id = str(payload["event_id"])
        action = str(payload["action"])
        printer_id = str(payload["printer_id"])
        nonce = str(payload["nonce"])
        expires_at = datetime.utcfromtimestamp(int(payload["exp"]))
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ActionTokenError("Invalid action token") from None

    if action != expected_action:
        raise ActionTokenError("Invalid action token")
    if datetime.utcnow() > expires_at:
        raise ActionTokenError("Action token expired")

    existing = session.exec(
        select(ActionTokenNonce).where(ActionTokenNonce.nonce == nonce)
    ).first()
    if existing:
        raise ActionTokenError("Action token already used")

    claims = ActionTokenClaims(
        event_id=event_id,
        action=action,
        printer_id=printer_id,
        expires_at=expires_at,
        nonce=nonce,
    )

    if mark_used:
        session.add(
            ActionTokenNonce(
                nonce=nonce,
                event_id=event_id,
                action=action,
                printer_id=printer_id,
                expires_at=expires_at,
            )
        )
        session.commit()

    return claims
