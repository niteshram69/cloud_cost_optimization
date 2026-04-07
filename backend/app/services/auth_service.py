import hashlib
import logging
import secrets
import smtplib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.security import create_access_token, hash_password, verify_password
from backend.app.models import CloudProvider, LoginAudit, OTPCode, OTPPurpose, User, UserRole
from backend.app.schemas.auth import LoginRequest, PasswordResetConfirmRequest, RegisterRequest
from backend.app.services.account_service import AccountService
from backend.app.services.billing_service import BillingService
from backend.app.services.public_data_guard import is_public_dataset_user

logger = logging.getLogger(__name__)


@dataclass
class OTPIssueResult:
    expires_in_seconds: int
    otp_code: str | None
    debug_otp: str | None
    expires_at: datetime | None
    purpose: OTPPurpose


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def bootstrap_admin_user(self) -> User:
        account_service = AccountService(self.db)
        account_service.ensure_default_plans()

        admin_email = settings.bootstrap_admin_email.strip().lower()
        other_admins = self.db.scalars(
            select(User).where(User.role == UserRole.ADMIN, User.email != admin_email)
        ).all()
        for user in other_admins:
            user.role = UserRole.USER

        admin = self.db.scalar(select(User).where(User.email == admin_email))

        if admin:
            admin.name = settings.bootstrap_admin_name
            admin.company_name = settings.bootstrap_admin_company
            admin.cloud_provider = CloudProvider(settings.bootstrap_admin_cloud_provider)
            admin.hashed_password = hash_password(settings.bootstrap_admin_password)
            admin.role = UserRole.ADMIN
            admin.is_active = True
            self.db.commit()
            self.db.refresh(admin)
            account = account_service.ensure_user_account(admin)
            BillingService(self.db).ensure_open_cycle(account=account, plan=account.plan)
            return admin

        admin = User(
            name=settings.bootstrap_admin_name,
            email=admin_email,
            hashed_password=hash_password(settings.bootstrap_admin_password),
            company_name=settings.bootstrap_admin_company,
            cloud_provider=CloudProvider(settings.bootstrap_admin_cloud_provider),
            role=UserRole.ADMIN,
            is_active=True,
        )
        self.db.add(admin)
        self.db.commit()
        self.db.refresh(admin)
        account = account_service.ensure_user_account(admin)
        BillingService(self.db).ensure_open_cycle(account=account, plan=account.plan)
        return admin

    def request_registration_otp(self, email: str) -> OTPIssueResult:
        normalized_email = email.strip().lower()
        existing = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise ValueError("Email is already registered")
        if not settings.otp_enabled:
            return OTPIssueResult(
                expires_in_seconds=settings.otp_ttl_minutes * 60,
                otp_code=None,
                debug_otp=None,
                expires_at=None,
                purpose=OTPPurpose.REGISTRATION,
            )
        return self._issue_otp(normalized_email, OTPPurpose.REGISTRATION)

    def request_password_reset_otp(self, email: str) -> OTPIssueResult:
        normalized_email = email.strip().lower()
        if not settings.otp_enabled:
            return OTPIssueResult(
                expires_in_seconds=settings.otp_ttl_minutes * 60,
                otp_code=None,
                debug_otp=None,
                expires_at=None,
                purpose=OTPPurpose.PASSWORD_RESET,
            )
        existing = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            return self._issue_otp(normalized_email, OTPPurpose.PASSWORD_RESET)
        return OTPIssueResult(
            expires_in_seconds=settings.otp_ttl_minutes * 60,
            otp_code=None,
            debug_otp=None,
            expires_at=None,
            purpose=OTPPurpose.PASSWORD_RESET,
        )

    def confirm_password_reset(self, payload: PasswordResetConfirmRequest) -> None:
        normalized_email = payload.email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == normalized_email))
        if not user:
            raise ValueError("Invalid reset request")
        if settings.otp_enabled:
            if not payload.otp_code:
                raise ValueError("Invalid reset request")
            self._consume_otp(normalized_email, OTPPurpose.PASSWORD_RESET, payload.otp_code)
        user.hashed_password = hash_password(payload.new_password)
        self.db.commit()

    def register_user(self, payload: RegisterRequest) -> User:
        account_service = AccountService(self.db)
        account_service.ensure_default_plans()

        normalized_email = payload.email.strip().lower()
        existing = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing:
            raise ValueError("Email is already registered")

        if settings.otp_enabled:
            if not payload.otp_code:
                raise ValueError("Registration OTP is required")
            self._consume_otp(normalized_email, OTPPurpose.REGISTRATION, payload.otp_code)
        role = UserRole.USER
        if not settings.bootstrap_admin_enabled:
            total_users = self.db.query(User).count()
            role = UserRole.ADMIN if total_users == 0 else UserRole.USER

        user = User(
            name=payload.name,
            email=normalized_email,
            hashed_password=hash_password(payload.password),
            company_name=payload.company_name,
            cloud_provider=payload.cloud_provider,
            role=role,
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        account = account_service.ensure_user_account(user)
        BillingService(self.db).ensure_open_cycle(account=account, plan=account.plan)
        return user

    def authenticate_user(self, payload: LoginRequest) -> tuple[User, str]:
        normalized_email = payload.email.strip().lower()
        user = self.db.scalar(select(User).where(User.email == normalized_email))
        if not user or not verify_password(payload.password, user.hashed_password):
            raise ValueError("Invalid email or password")
        if is_public_dataset_user(user):
            raise ValueError("Invalid email or password")
        if not user.is_active:
            raise ValueError("User account is inactive")

        account_service = AccountService(self.db)
        account_service.ensure_default_plans()
        account = account_service.ensure_user_account(user)
        BillingService(self.db).ensure_open_cycle(account=account, plan=account.plan)

        access_token = create_access_token(subject=str(user.id), role=user.role.value)
        return user, access_token

    def record_login_audit(self, *, user_id: int, ip_address: str | None, user_agent: str | None) -> None:
        audit = LoginAudit(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit)
        self.db.commit()

    def _issue_otp(self, email: str, purpose: OTPPurpose) -> OTPIssueResult:
        now = datetime.now(UTC)
        previous_active = self.db.scalar(
            select(OTPCode)
            .where(
                OTPCode.email == email,
                OTPCode.purpose == purpose,
                OTPCode.consumed_at.is_(None),
                OTPCode.expires_at > now,
            )
            .order_by(OTPCode.created_at.desc())
        )
        if previous_active:
            elapsed = (now - previous_active.created_at).total_seconds()
            if elapsed < settings.otp_resend_cooldown_seconds:
                return OTPIssueResult(
                    expires_in_seconds=settings.otp_ttl_minutes * 60,
                    otp_code=None,
                    debug_otp=None,
                    expires_at=previous_active.expires_at,
                    purpose=purpose,
                )

        otp_code = self._generate_otp()
        expires_at = now + timedelta(minutes=settings.otp_ttl_minutes)

        otp_record = OTPCode(
            email=email,
            purpose=purpose,
            code_hash=self._hash_otp(email=email, purpose=purpose, otp_code=otp_code),
            max_attempts=settings.otp_max_attempts,
            expires_at=expires_at,
        )
        self.db.add(otp_record)
        self.db.commit()

        debug_otp = otp_code if settings.environment != "production" else None
        return OTPIssueResult(
            expires_in_seconds=settings.otp_ttl_minutes * 60,
            otp_code=otp_code,
            debug_otp=debug_otp,
            expires_at=expires_at,
            purpose=purpose,
        )

    def _consume_otp(self, email: str, purpose: OTPPurpose, otp_code: str) -> None:
        now = datetime.now(UTC)
        otp_record = self.db.scalar(
            select(OTPCode)
            .where(
                OTPCode.email == email,
                OTPCode.purpose == purpose,
                OTPCode.consumed_at.is_(None),
            )
            .order_by(OTPCode.created_at.desc())
        )
        if not otp_record:
            raise ValueError("OTP is invalid or has expired")
        if otp_record.expires_at <= now:
            raise ValueError("OTP is invalid or has expired")
        if otp_record.attempt_count >= otp_record.max_attempts:
            raise ValueError("OTP retry limit exceeded. Request a new OTP")

        expected_hash = self._hash_otp(email=email, purpose=purpose, otp_code=otp_code)
        if otp_record.code_hash != expected_hash:
            otp_record.attempt_count += 1
            self.db.commit()
            raise ValueError("Invalid OTP code")

        otp_record.consumed_at = now
        self.db.commit()

    def _hash_otp(self, email: str, purpose: OTPPurpose, otp_code: str) -> str:
        digest = hashlib.sha256()
        digest.update(f"{email}:{purpose.value}:{otp_code}:{settings.jwt_secret_key}".encode("utf-8"))
        return digest.hexdigest()

    def _generate_otp(self) -> str:
        max_value = 10**settings.otp_length
        return f"{secrets.randbelow(max_value):0{settings.otp_length}d}"

    def send_otp_email(
        self,
        email: str,
        purpose: OTPPurpose,
        otp_code: str,
        expires_at: datetime,
    ) -> None:
        subject = (
            "Cloudteck registration OTP"
            if purpose == OTPPurpose.REGISTRATION
            else "Cloudteck password reset OTP"
        )
        body = (
            "Use the following one-time password to continue.\n\n"
            f"OTP: {otp_code}\n"
            f"Expires at: {expires_at.isoformat()}\n\n"
            "If you did not request this, ignore this email."
        )

        if not settings.smtp_host or not settings.smtp_from_email:
            logger.warning(
                "SMTP is not configured. OTP generated for %s (%s): %s",
                email,
                purpose.value,
                otp_code,
            )
            return

        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = settings.smtp_from_email
        message["To"] = email
        message.set_content(body)

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(message)
        except Exception as exc:
            logger.exception("Failed to send OTP email for %s", email)
            if settings.environment == "production":
                raise ValueError("Unable to dispatch OTP at this time") from exc
