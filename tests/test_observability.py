from __future__ import annotations

import pytest
from fastapi import HTTPException

from server import app as server_app


def test_session_creation_rejects_role_mismatch(world: dict) -> None:
    server_app._SESSIONS.clear()

    with pytest.raises(HTTPException) as exc_info:
        server_app.create_session(
            server_app.SessionCreate(user_id=9002, role="shopper")
        )

    assert exc_info.value.status_code == 403


def test_token_cannot_authorize_different_session(world: dict) -> None:
    server_app._SESSIONS.clear()
    first = server_app.create_session(
        server_app.SessionCreate(user_id=1, role="shopper")
    )
    second = server_app.create_session(
        server_app.SessionCreate(user_id=1, role="shopper")
    )

    with pytest.raises(HTTPException) as exc_info:
        server_app._authorize(
            second["session_id"],
            f"Bearer {first['token']}",
        )

    assert exc_info.value.status_code == 403
