"""
src/services/auth_service.py
Authentication Service managing PBKDF2 salted password hashing, user login,
sign-out session management, and demo accounts.
"""

import hashlib
import os
import secrets
from datetime import datetime, timezone
from typing import Optional, Dict
import uuid

from sqlalchemy import func
from src.infrastructure.storage.repository import DatabaseEngine
from src.infrastructure.storage.models import UserModel, EngineeringDepartmentModel
from src.core.dtos.auth_dtos import UserDTO, SessionTokenDTO
from src.core.exceptions.auth_exceptions import (
    InvalidCredentialsError,
    UserNotFoundError,
    UserAlreadyExistsError,
    WeakPasswordError,
    DepartmentNotFoundError,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger("AuthService")

# Minimum password policy for self-service registration.
_MIN_PASSWORD_LENGTH = 8


class AuthService:
    """
    Authentication Service managing sign in, sign out, password verification,
    and user session state.
    """

    def __init__(self, db_engine: DatabaseEngine) -> None:
        self.db_engine = db_engine
        self._active_sessions: Dict[str, SessionTokenDTO] = {}
        self._seed_demo_users()

    def _hash_password(self, password: str, salt: Optional[bytes] = None) -> tuple[str, str]:
        """Hashes password using PBKDF2 with SHA-256 and salt."""
        if salt is None:
            salt = os.urandom(16)
        pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
        return pwd_hash.hex(), salt.hex()

    def _verify_password(self, password: str, stored_hash: str, stored_salt_hex: str) -> bool:
        """Verifies input password against stored salt and hash."""
        salt = bytes.fromhex(stored_salt_hex)
        input_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000).hex()
        return secrets.compare_digest(input_hash, stored_hash)

    def _seed_demo_users(self) -> None:
        """Seeds default demo accounts into SQLite database if empty."""
        with self.db_engine.get_session() as session:
            try:
                if session.query(UserModel).count() == 0:
                    # Resolve department ids by name (departments are seeded on DB init).
                    dept_rows = session.query(EngineeringDepartmentModel).all()
                    dept_by_name = {d.name: d.id for d in dept_rows}

                    # (username, display, email, plain_pwd, role, department_name)
                    # A None department means the account is unscoped (sees all departments).
                    demo_accounts = [
                        ("admin", "Admin User", "admin@ucc.com", "Password123!", "Lead Engineer", None),
                        ("soham", "Soham Patil", "soham@ucc.com", "Password123!", "Backend Lead", "Piping Engineering"),
                        ("reviewer", "Review Engineer", "reviewer@ucc.com", "Password123!", "Reviewer", "Electrical Engineering"),
                    ]

                    for uname, display, email, plain_pwd, role, dept_name in demo_accounts:
                        pwd_hash, salt_hex = self._hash_password(plain_pwd)
                        user_record = UserModel(
                            id=f"USR-{uuid.uuid4().hex[:8].upper()}",
                            username=uname,
                            display_name=display,
                            email=email,
                            password_hash=pwd_hash,
                            salt=salt_hex,
                            role=role,
                            department_id=dept_by_name.get(dept_name) if dept_name else None,
                            is_active=True,
                            created_at=datetime.now(timezone.utc),
                        )
                        session.add(user_record)

                    session.commit()
                    logger.info("Seeded demo user accounts into database (admin, soham, reviewer).")
            except Exception as e:
                session.rollback()
                logger.error(f"Failed to seed demo users: {e}")

    def register_user(
        self,
        username: str,
        display_name: str,
        email: str,
        password: str,
        department_id: Optional[str] = None,
        role: str = "Reviewer",
    ) -> UserDTO:
        """
        Register a new department-scoped user account.

        Raises:
            UserAlreadyExistsError: username or email already registered.
            WeakPasswordError: password does not meet the minimum policy.
            DepartmentNotFoundError: department_id does not reference a real department.
        """
        username = (username or "").strip()
        display_name = (display_name or "").strip()
        email = (email or "").strip().lower()

        if not username or not email or not password:
            raise WeakPasswordError("Username, email, and password are all required.")

        if len(password) < _MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(
                f"Password must be at least {_MIN_PASSWORD_LENGTH} characters long."
            )

        with self.db_engine.get_session() as session:
            uname_clean = username.lower()
            existing = session.query(UserModel).filter(
                (func.lower(UserModel.username) == uname_clean) |
                (func.lower(UserModel.email) == email)
            ).first()
            if existing:
                raise UserAlreadyExistsError(
                    "An account with that username or email already exists."
                )

            resolved_dept_id = None
            dept_name = None
            if department_id:
                dept_row = session.get(EngineeringDepartmentModel, department_id)
                if not dept_row:
                    # Fall back to matching by name in case an id/name was passed.
                    dept_row = session.query(EngineeringDepartmentModel).filter(
                        EngineeringDepartmentModel.name == department_id
                    ).first()
                if not dept_row:
                    raise DepartmentNotFoundError("Selected engineering department is not valid.")
                resolved_dept_id = dept_row.id
                dept_name = dept_row.name

            pwd_hash, salt_hex = self._hash_password(password)
            user_record = UserModel(
                id=f"USR-{uuid.uuid4().hex[:8].upper()}",
                username=username,
                display_name=display_name or username,
                email=email,
                password_hash=pwd_hash,
                salt=salt_hex,
                role=role,
                department_id=resolved_dept_id,
                is_active=True,
                created_at=datetime.now(timezone.utc),
            )
            session.add(user_record)
            session.commit()
            logger.info(
                f"Registered new user '{username}' (dept='{dept_name or 'Unassigned'}', role='{role}')."
            )

            return UserDTO(
                user_id=user_record.id,
                username=user_record.username,
                email=user_record.email,
                role=user_record.role,
                display_name=user_record.display_name,
                department_id=user_record.department_id,
                department_name=dept_name or "Unassigned",
                is_authenticated=False,
            )

    def authenticate_user(self, username_or_email: str, password: str) -> SessionTokenDTO:
        """
        Authenticates user with username/email and password.

        Returns:
            SessionTokenDTO: Active session container.

        Raises:
            InvalidCredentialsError: If username or password does not match.
        """
        with self.db_engine.get_session() as session:
            uname_clean = username_or_email.strip().lower()
            user_record = session.query(UserModel).filter(
                (func.lower(UserModel.username) == uname_clean) |
                (func.lower(UserModel.email) == uname_clean)
            ).first()

            if not user_record:
                logger.warning(f"Failed login attempt for unknown user: {username_or_email}")
                raise InvalidCredentialsError("Invalid username or password.")

            if not user_record.password_hash or not user_record.salt:
                logger.warning(f"User '{username_or_email}' has no password set.")
                raise InvalidCredentialsError("Invalid username or password.")

            if not self._verify_password(password, user_record.password_hash, user_record.salt):
                logger.warning(f"Invalid password for user: {username_or_email}")
                raise InvalidCredentialsError("Invalid username or password.")

            # Update last login
            user_record.last_login = datetime.now(timezone.utc)
            session.commit()

            user_dto = UserDTO(
                user_id=user_record.id,
                username=user_record.username,
                email=user_record.email,
                role=user_record.role,
                display_name=user_record.display_name,
                department_id=user_record.department_id,
                department_name=(
                    user_record.department_rel.name
                    if user_record.department_rel else "Unassigned"
                ),
                is_authenticated=True,
                last_login=user_record.last_login,
            )

            # Generate session token
            token_str = f"TOK-{secrets.token_hex(16)}"
            session_dto = SessionTokenDTO(
                token=token_str,
                user=user_dto,
                created_at=datetime.now(timezone.utc),
            )
            self._active_sessions[token_str] = session_dto

            logger.info(f"User '{user_record.username}' ({user_record.role}) signed in successfully.")
            return session_dto

    def sign_out(self, token: str) -> bool:
        """Invalidates an active user session token."""
        if token in self._active_sessions:
            user = self._active_sessions[token].user
            del self._active_sessions[token]
            logger.info(f"User '{user.username}' signed out successfully.")
            return True
        return False

    def validate_session(self, token: str) -> Optional[UserDTO]:
        """Validates token and returns active UserDTO if valid."""
        if token in self._active_sessions:
            return self._active_sessions[token].user
        return None
