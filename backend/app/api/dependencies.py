from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..errors import auth_required
from ..models import User
from ..security.tokens import decode_auth_token

bearer = HTTPBearer(auto_error=False)


async def current_user_id(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> int:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_required()
    settings = request.app.state.settings
    user_id = decode_auth_token(credentials.credentials, settings.app_token_secret.get_secret_value())
    with request.app.state.database.session_factory() as session:
        if session.get(User, user_id) is None:
            raise auth_required("用户不存在")
    return user_id
