"""Test signed action tokens."""
from datetime import datetime, timedelta

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

from app.core.config import AppConfig
from app.models.event import ActionTokenNonce
from app.security import ActionTokenError, create_action_token, verify_action_token


def make_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_action_token_verifies_and_cannot_be_replayed():
    config = AppConfig()
    config.security.action_signing_secret = "test-secret"
    session = make_session()
    token = create_action_token(config, "event_1", "pause", "printer_1")

    claims = verify_action_token(token, "pause", config, session)

    assert claims.event_id == "event_1"
    assert claims.action == "pause"
    assert claims.printer_id == "printer_1"
    assert len(session.exec(select(ActionTokenNonce)).all()) == 1

    with pytest.raises(ActionTokenError):
        verify_action_token(token, "pause", config, session)


def test_action_token_rejects_wrong_action_and_expiration():
    config = AppConfig()
    config.security.action_signing_secret = "test-secret"
    session = make_session()
    wrong_action = create_action_token(config, "event_1", "ignore", "printer_1")
    expired = create_action_token(
        config,
        "event_1",
        "pause",
        "printer_1",
        expires_at=datetime.utcnow() - timedelta(hours=1),
    )

    with pytest.raises(ActionTokenError):
        verify_action_token(wrong_action, "pause", config, session)

    with pytest.raises(ActionTokenError):
        verify_action_token(expired, "pause", config, session)
