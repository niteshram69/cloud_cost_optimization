"""Custom exception classes for the application."""


class CostIntelException(Exception):
    """Base exception for all application errors."""
    
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(CostIntelException):
    """Raised when authentication fails."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)


class AuthorizationError(CostIntelException):
    """Raised when user lacks permission."""
    
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403)


class ResourceNotFoundError(CostIntelException):
    """Raised when a requested resource doesn't exist."""
    
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            f"{resource_type} with id '{resource_id}' not found",
            status_code=404,
        )


class ValidationError(CostIntelException):
    """Raised when input validation fails."""
    
    def __init__(self, message: str = "Validation failed"):
        super().__init__(message, status_code=422)


class DuplicateResourceError(CostIntelException):
    """Raised when attempting to create a duplicate resource."""
    
    def __init__(self, resource_type: str, field: str, value: str):
        super().__init__(
            f"{resource_type} with {field} '{value}' already exists",
            status_code=409,
        )


class ProcessingError(CostIntelException):
    """Raised when data processing fails."""
    
    def __init__(self, message: str = "Processing failed"):
        super().__init__(message, status_code=500)


class WebhookDeliveryError(CostIntelException):
    """Raised when webhook delivery fails after all retries."""
    
    def __init__(self, message: str = "Webhook delivery failed"):
        super().__init__(message, status_code=502)
