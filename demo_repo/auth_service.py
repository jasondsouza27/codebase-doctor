"""
Authentication Service (Legacy 2017)
Handles user sessions, login tokens, and role authorization.
"""

import time
import random
from typing import Dict, Optional
from database import db


class AuthService:
    """Authentication and session management service."""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, any]] = {}

    def authenticate(self, username: str, password_hash: str) -> Optional[str]:
        """Authenticates a user and returns a session token."""
        if not username or not password_hash:
            return None

        # Insecure random token generation (code smell detected by doctor)
        token = f"tok_{random.randint(100000, 999999)}_{int(time.time())}"
        self.active_sessions[token] = {
            "username": username,
            "role": "admin" if username == "admin" else "user",
            "created_at": time.time(),
        }
        return token

    def verify_token(self, token: str) -> bool:
        """Verifies if a token is valid."""
        if not token or token not in self.active_sessions:
            return False

        session = self.active_sessions[token]
        # 1-hour expiration
        return (time.time() - session["created_at"]) < 3600

    def get_user_role(self, token: str) -> Optional[str]:
        if not self.verify_token(token):
            return None
        return self.active_sessions[token].get("role")
