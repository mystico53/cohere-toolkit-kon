import datetime

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.config.auth import get_auth_strategy
from backend.database_models import Blacklist, get_session
from backend.services.auth.jwt import JWTService
from backend.services.auth.utils import get_or_create_user

UPDATE_TOKEN_HEADER = "X-Toolkit-Auth-Update"


def validate_authorization(
    request: Request, response: Response, session: Session = Depends(get_session)
) -> dict:
    """
    Validate that the request has the `Authorization` header, used for requests
    that require authentication.

    Args:
        request (Request): The request to validate

    Raises:
        HTTPException: If no `Authorization` header.

    Returns:
        dict: Decoded payload.
    """

    # 1. Check if `Authorization` header is present
    authorization = request.headers.get("Authorization")
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer <token> required in request headers.",
        )

    # 2. Check if `Authorization` header is well-formed and contains a `Bearer` token.
    scheme, token = authorization.split(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Authorization: Bearer <token> required in request headers.",
        )

    decoded_token = JWTService().decode_jwt(token)

    # 3. Check if JWT token can be decoded
    if decoded_token is None or any(
        [
            "context" not in decoded_token,
            "jti" not in decoded_token,
            "exp" not in decoded_token,
            "strategy" not in decoded_token,
        ]
    ):
        raise HTTPException(status_code=401, detail="Bearer token is invalid.")

    # 4. Check if token is blacklisted
    blacklist = (
        session.query(Blacklist)
        .filter(Blacklist.token_id == decoded_token["jti"])
        .first()
    )

    if blacklist is not None:
        raise HTTPException(status_code=401, detail="Bearer token is blacklisted.")

    # 5. Check if token is expired - if so then try refresh logic
    expiry_datetime = datetime.datetime.fromtimestamp(decoded_token["exp"])
    strategy_name = decoded_token["strategy"]
    now = datetime.datetime.utcnow()

    if now > expiry_datetime:
        strategy = get_auth_strategy(strategy_name)

        if not strategy:
            raise HTTPException(
                status_code=400,
                detail=f"Tried refreshing token, but Auth strategy {strategy_name} is disabled.",
            )

        if not hasattr(strategy, "refresh"):
            raise HTTPException(
                status_code=400,
                detail=f"Tried refreshing token, but Auth strategy {strategy_name} does not have a refresh method implemented.",
            )

        try:
            userinfo = strategy.refresh(request)
            user = get_or_create_user(session, userinfo)
            token = JWTService().create_and_encode_jwt(user, strategy_name)

            # Set new token in response
            response.headers[UPDATE_TOKEN_HEADER] = token

            return token
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Could not create user and encode JWT token.",
            )

    return decoded_token
