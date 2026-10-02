"""
OTP service with secure generation, expiry control, rate limiting and
brute-force protection.

Storage is in-memory for simplicity, but isolated behind a dedicated service
class so replacing it with Redis/DB later is straightforward.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from typing import Deque, Dict
import hashlib
import hmac
import secrets
import re
import logging
from ..config import settings

logger = logging.getLogger(__name__)


@dataclass
class OtpRecord:
    """One OTP record per phone number."""

    otp_hash: str
    salt: str
    expires_at: datetime
    created_at: datetime


class OtpError(Exception):
    """Base OTP service exception."""


class OtpRateLimitError(OtpError):
    """Too many OTP generation requests in a short window."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class OtpExpiredError(OtpError):
    """OTP exists but is expired."""


class OtpInvalidError(OtpError):
    """OTP is missing or incorrect."""


class OtpBruteForceBlockedError(OtpError):
    """Too many failed verify attempts for this phone."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class OtpService:
    """
    In-memory OTP workflow service.

    Security controls included:
    - 6-digit cryptographically random OTP
    - 5 minute expiry (extended in development)
    - max 3 send requests per minute per phone
    - max 5 failed verify attempts per 5 minutes per phone
    """

    OTP_LENGTH = 6
    OTP_EXPIRY_SECONDS = 5 * 60
    SEND_RATE_LIMIT_COUNT = 3
    SEND_RATE_LIMIT_WINDOW_SECONDS = 60
    VERIFY_FAIL_LIMIT_COUNT = 5
    VERIFY_FAIL_WINDOW_SECONDS = 5 * 60

    def __init__(self) -> None:
        # Active OTPs keyed by normalized phone
        self._otp_store: Dict[str, OtpRecord] = {}

        # Rate-limit history keyed by normalized phone
        self._send_attempts: Dict[str, Deque[datetime]] = defaultdict(deque)
        self._verify_failures: Dict[str, Deque[datetime]] = defaultdict(deque)

    def normalize_phone(self, phone: str) -> str:
        """Normalize local PK and generic phone input into a consistent key."""
        digits = re.sub(r"[^0-9+]", "", phone or "")

        # Handle +92 with accidental extra zero: +920300... -> +92300...
        if digits.startswith("+920") and len(digits) > 4:
            return f"+92{digits[4:]}"
        if digits.startswith("+92"):
            return digits
        if digits.startswith("+"):
            return digits
        if digits.startswith("03") and len(digits) == 11:
            return f"+92{digits[1:]}"
        if digits.startswith("920") and len(digits) > 3:
            return f"+92{digits[3:]}"
        if digits.startswith("92") and len(digits) == 12:
            return f"+{digits}"
        if digits.startswith("3") and len(digits) == 10:
            return f"+92{digits}"
        if digits.startswith("0") and len(digits) >= 10:
            return f"+92{digits[1:]}"

        return digits

    def send_otp(self, phone: str) -> tuple[int, str]:
        """
        Generate and store a new OTP for a phone number.

        Returns:
            Tuple of (OTP expiry in seconds, generated OTP code).

        Raises:
            OtpRateLimitError: if rate limit is exceeded.
        """
        now = self._utc_now()
        normalized_phone = self.normalize_phone(phone)

        self._cleanup_phone(normalized_phone, now)
        self._assert_send_rate_limit(normalized_phone, now)

        otp = self._generate_otp()
        salt = secrets.token_hex(16)
        otp_hash = self._hash_otp(otp, salt)

        # In development, give 1 hour so the user has plenty of time to test
        is_dev = getattr(settings, "DEBUG", False) or getattr(settings, "OTP_EXPOSE_IN_RESPONSE", False)
        expiry_seconds = 3600 if is_dev else self.OTP_EXPIRY_SECONDS

        self._otp_store[normalized_phone] = OtpRecord(
            otp_hash=otp_hash,
            salt=salt,
            created_at=now,
            expires_at=now + timedelta(seconds=expiry_seconds),
        )

        # Record this request for rate limiting.
        self._send_attempts[normalized_phone].append(now)

        logger.info("[OTP] Generated OTP for phone=%s debugOtp=%s (expires in %ds)", normalized_phone, otp, expiry_seconds)
        return expiry_seconds, otp

    def verify_otp(self, phone: str, otp: str) -> None:
        """
        Verify OTP for a phone number.

        Raises:
            OtpExpiredError: OTP exists but expired.
            OtpInvalidError: OTP missing or incorrect.
            OtpBruteForceBlockedError: too many failed attempts.
        """
        now = self._utc_now()
        normalized_phone = self.normalize_phone(phone)
        otp_clean = str(otp or "").strip()

        # Allow test master OTP in development mode
        is_dev = getattr(settings, "DEBUG", False) or getattr(settings, "OTP_EXPOSE_IN_RESPONSE", False)
        if is_dev and otp_clean in ("123456", "000000"):
            logger.info("[OTP DEV] Verified with universal test OTP for phone=%s", normalized_phone)
            self._otp_store.pop(normalized_phone, None)
            self._verify_failures.pop(normalized_phone, None)
            return

        self._cleanup_phone(normalized_phone, now)
        self._assert_verify_not_blocked(normalized_phone, now)

        record = self._otp_store.get(normalized_phone)
        if not record:
            # Suffix match on last 10 digits to be resilient to country code formatting differences
            last_10 = re.sub(r"[^0-9]", "", normalized_phone)[-10:]
            if len(last_10) == 10:
                for key, rec in list(self._otp_store.items()):
                    if key.endswith(last_10):
                        record = rec
                        normalized_phone = key
                        break

        if not record:
            logger.warning("[OTP] Not found for phone=%s. Active store keys: %s", normalized_phone, list(self._otp_store.keys()))
            raise OtpInvalidError("OTP not found for this phone number")

        if now > record.expires_at:
            del self._otp_store[normalized_phone]
            raise OtpExpiredError("OTP has expired. Please request a new OTP")

        candidate_hash = self._hash_otp(otp_clean, record.salt)
        if not hmac.compare_digest(candidate_hash, record.otp_hash):
            self._verify_failures[normalized_phone].append(now)
            self._assert_verify_not_blocked(normalized_phone, now)
            raise OtpInvalidError("Incorrect OTP")

        # Success: consume OTP and clear failure history.
        del self._otp_store[normalized_phone]
        self._verify_failures.pop(normalized_phone, None)
        logger.info("[OTP] Successfully verified OTP for phone=%s", normalized_phone)

    def _assert_send_rate_limit(self, phone: str, now: datetime) -> None:
        attempts = self._send_attempts[phone]
        window_start = now - timedelta(seconds=self.SEND_RATE_LIMIT_WINDOW_SECONDS)

        while attempts and attempts[0] < window_start:
            attempts.popleft()

        if len(attempts) >= self.SEND_RATE_LIMIT_COUNT:
            oldest_attempt = attempts[0]
            retry_after = self.SEND_RATE_LIMIT_WINDOW_SECONDS - int((now - oldest_attempt).total_seconds())
            raise OtpRateLimitError(
                "Too many OTP requests. Please try again shortly",
                max(retry_after, 1),
            )

    def _assert_verify_not_blocked(self, phone: str, now: datetime) -> None:
        failures = self._verify_failures[phone]
        window_start = now - timedelta(seconds=self.VERIFY_FAIL_WINDOW_SECONDS)

        while failures and failures[0] < window_start:
            failures.popleft()

        if len(failures) >= self.VERIFY_FAIL_LIMIT_COUNT:
            oldest_failure = failures[0]
            retry_after = self.VERIFY_FAIL_WINDOW_SECONDS - int((now - oldest_failure).total_seconds())
            raise OtpBruteForceBlockedError(
                "Too many invalid attempts. Please wait before retrying",
                max(retry_after, 1),
            )

    def _cleanup_phone(self, phone: str, now: datetime) -> None:
        """Cleanup stale OTP entries for this phone only."""
        record = self._otp_store.get(phone)
        if record and now > record.expires_at:
            self._otp_store.pop(phone, None)

    def _generate_otp(self) -> str:
        """Generate secure 6-digit OTP with leading zeros preserved."""
        return f"{secrets.randbelow(10 ** self.OTP_LENGTH):0{self.OTP_LENGTH}d}"

    def _hash_otp(self, otp: str, salt: str) -> str:
        payload = f"{salt}:{otp}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _utc_now(self) -> datetime:
        return datetime.now(timezone.utc)
