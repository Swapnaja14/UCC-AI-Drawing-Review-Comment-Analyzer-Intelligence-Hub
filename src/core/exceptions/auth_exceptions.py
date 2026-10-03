"""
src/core/exceptions/auth_exceptions.py
Domain exceptions for Authentication operations.
"""

class AuthError(Exception):
    """Base exception for authentication errors."""
    pass

class InvalidCredentialsError(AuthError):
    """Raised when username or password is invalid."""
    pass

class UserNotFoundError(AuthError):
    """Raised when requested user account does not exist."""
    pass

class UnauthorizedError(AuthError):
    """Raised when user attempts an unauthorized operation."""
    pass

class UserAlreadyExistsError(AuthError):
    """Raised when registration targets a username or email that is already taken."""
    pass

class WeakPasswordError(AuthError):
    """Raised when a registration password does not meet the minimum strength policy."""
    pass

class DepartmentNotFoundError(AuthError):
    """Raised when a referenced engineering department does not exist."""
    pass
