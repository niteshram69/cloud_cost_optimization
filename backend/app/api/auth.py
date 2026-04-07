from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.database import get_db
from backend.app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    OtpDispatchResponse,
    OtpRequest,
    PasswordResetConfirmRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register/request-otp", response_model=OtpDispatchResponse, status_code=status.HTTP_202_ACCEPTED)
def request_registration_otp(
    payload: OtpRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> OtpDispatchResponse:
    if not settings.otp_enabled:
        return OtpDispatchResponse(
            message="OTP is currently disabled. Complete registration directly.",
            expires_in_seconds=0,
            debug_otp=None,
        )

    service = AuthService(db)
    try:
        result = service.request_registration_otp(str(payload.email))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if result.otp_code and result.expires_at:
        # Fire-and-forget dispatch to avoid request latency and allow retries.
        background_tasks.add_task(
            service.send_otp_email,
            email=str(payload.email),
            purpose=result.purpose,
            otp_code=result.otp_code,
            expires_at=result.expires_at,
        )

    return OtpDispatchResponse(
        message="OTP sent to email. Verify and complete registration.",
        expires_in_seconds=result.expires_in_seconds,
        debug_otp=result.debug_otp,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    service = AuthService(db)
    try:
        user = service.register_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    service = AuthService(db)
    try:
        user, access_token = service.authenticate_user(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    service.record_login_audit(
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    return TokenResponse(access_token=access_token, user=UserResponse.model_validate(user))


@router.post(
    "/password-reset/request-otp",
    response_model=OtpDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_password_reset_otp(
    payload: OtpRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> OtpDispatchResponse:
    if not settings.otp_enabled:
        return OtpDispatchResponse(
            message="OTP is currently disabled. Submit reset form directly.",
            expires_in_seconds=0,
            debug_otp=None,
        )

    service = AuthService(db)
    try:
        result = service.request_password_reset_otp(str(payload.email))
    except ValueError:
        result = None
    if result and result.otp_code and result.expires_at:
        background_tasks.add_task(
            service.send_otp_email,
            email=str(payload.email),
            purpose=result.purpose,
            otp_code=result.otp_code,
            expires_at=result.expires_at,
        )

    return OtpDispatchResponse(
        message="If the account exists, a password reset OTP has been sent.",
        expires_in_seconds=(result.expires_in_seconds if result else 600),
        debug_otp=(result.debug_otp if result else None),
    )


@router.post("/password-reset/confirm", response_model=MessageResponse)
def confirm_password_reset(payload: PasswordResetConfirmRequest, db: Session = Depends(get_db)) -> MessageResponse:
    service = AuthService(db)
    try:
        service.confirm_password_reset(payload)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP. Please request a new code.",
        )

    return MessageResponse(message="Password reset successful")
