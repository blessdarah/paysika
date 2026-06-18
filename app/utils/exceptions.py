class APIError(Exception):
    """Base exception for API errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class ConflictError(APIError):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, status_code=401)


class ForbiddenError(APIError):
    def __init__(self, message: str = "Forbidden"):
        super().__init__(message, status_code=403)


class ValidationError(APIError):
    def __init__(self, message: str = "Validation error"):
        super().__init__(message, status_code=422)


class InsufficientFundsError(APIError):
    def __init__(self, message: str = "Insufficient funds"):
        super().__init__(message, status_code=422)


class InvalidTransactionStateError(APIError):
    def __init__(self, message: str = "Invalid transaction state"):
        super().__init__(message, status_code=409)


class AccountNotFoundError(APIError):
    def __init__(self, message: str = "Account not found"):
        super().__init__(message, status_code=404)


class CurrencyMismatchError(APIError):
    def __init__(self, message: str = "Currency mismatch"):
        super().__init__(message, status_code=422)
