from dataclasses import dataclass

from fastapi import HTTPException, status

from app.deps import get_supabase, get_supabase_auth


@dataclass
class MintedSession:
    access_token: str
    refresh_token: str
    expires_in: int


def mint_session_for_email(email: str) -> MintedSession:
    resolved = (email or "").strip()
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account has no email; cannot impersonate",
        )
    admin = get_supabase()
    try:
        link = admin.auth.admin.generate_link({"type": "magiclink", "email": resolved})
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        ) from exc

    props = getattr(link, "properties", None)
    email_otp = getattr(props, "email_otp", None) if props else None
    hashed = getattr(props, "hashed_token", None) if props else None
    if not email_otp and not hashed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        )

    auth_client = get_supabase_auth()
    try:
        if email_otp:
            verified = auth_client.auth.verify_otp(
                {"email": resolved, "token": email_otp, "type": "magiclink"}
            )
        else:
            verified = auth_client.auth.verify_otp(
                {"token_hash": hashed, "type": "magiclink"}
            )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        ) from exc

    session = getattr(verified, "session", None)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth service temporarily unreachable. Please try again.",
        )
    return MintedSession(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        expires_in=session.expires_in or 3600,
    )
