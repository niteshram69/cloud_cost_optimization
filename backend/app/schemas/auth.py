from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.app.models.enums import CloudProvider, UserRole


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    company_name: str = Field(min_length=2, max_length=255)
    cloud_provider: CloudProvider
    otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")

    @field_validator("cloud_provider", mode="before")
    @classmethod
    def normalize_cloud_provider(cls, value: str | CloudProvider) -> str | CloudProvider:
        if isinstance(value, CloudProvider):
            return value
        if isinstance(value, str):
            normalized = value.strip().upper()
            aliases = {
                "AZURE": "AZURE",
                "AWS": "AWS",
                "GCP": "GCP",
                "GOOGLE": "GCP",
                "GOOGLE_CLOUD": "GCP",
                "MULTI": "MULTI",
                "MULTI_CLOUD": "MULTI",
                "MULTICLOUD": "MULTI",
                "ALL": "MULTI",
            }
            return aliases.get(normalized, "MULTI")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("name", "company_name", mode="before")
    @classmethod
    def trim_text_fields(cls, value: str) -> str:
        return str(value).strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class OtpRequest(BaseModel):
    email: EmailStr


class OtpDispatchResponse(BaseModel):
    message: str
    expires_in_seconds: int
    debug_otp: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    otp_code: str | None = Field(default=None, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=128)


class MessageResponse(BaseModel):
    message: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: EmailStr
    company_name: str
    cloud_provider: CloudProvider
    role: UserRole
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
