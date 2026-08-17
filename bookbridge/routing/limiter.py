"""Strict Token & Request Rate Limiter (RPM, TPM, RPD) with Sliding Window Pacing."""

import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import time
from typing import Deque, Dict, Optional, Tuple

from bookbridge.database.repositories.credential_repo import CredentialRepository
from bookbridge.models.provider import ProviderCredentialMetadata

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Thread-safe and async-safe Sliding Window Rate Limiter.
    Strictly enforces:
      1. RPM (Requests Per Minute)
      2. TPM (Tokens Per Minute)
      3. RPD (Requests Per Day)
      4. Inter-request pacing delay
    """

    def __init__(self, credential_repo: Optional[CredentialRepository] = None):
        self.credential_repo = credential_repo or CredentialRepository()
        # Per-credential sliding window for last 60 seconds: deque of (timestamp_seconds, tokens_count)
        self._sliding_windows: Dict[str, Deque[Tuple[float, int]]] = {}
        self._last_request_time: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._daily_counts: Dict[str, Tuple[float, int]] = {}  # cred_id -> (cache_timestamp, count)

    def _get_lock(self, cred_id: str) -> asyncio.Lock:
        if cred_id not in self._locks:
            self._locks[cred_id] = asyncio.Lock()
        return self._locks[cred_id]

    def _clean_sliding_window(self, cred_id: str, now: float) -> Deque[Tuple[float, int]]:
        if cred_id not in self._sliding_windows:
            self._sliding_windows[cred_id] = deque()
        window = self._sliding_windows[cred_id]
        cutoff = now - 60.0
        while window and window[0][0] <= cutoff:
            window.popleft()
        return window

    def get_24h_request_count(self, cred_id: str) -> int:
        now = time.time()
        if cred_id in self._daily_counts:
            cached_at, count = self._daily_counts[cred_id]
            if now - cached_at < 15.0:  # Cache for 15s to reduce DB reads
                return count

        try:
            count = self.credential_repo.get_credential_24h_request_count(cred_id)
            self._daily_counts[cred_id] = (now, count)
            return count
        except Exception:
            return 0

    def estimate_tokens(self, text: str) -> int:
        """Conservative token count estimation for English prompt + system prompt + Arabic output."""
        # System instructions ~350 tokens, input text ~1 token / 3 chars, output ~1.2x input
        base_chars = len(text) if text else 0
        input_tokens = max(10, int(base_chars / 3.0))
        output_tokens = max(20, int(input_tokens * 1.3))
        system_overhead = 350
        return input_tokens + output_tokens + system_overhead

    def check_capacity(
        self, cred: ProviderCredentialMetadata, estimated_tokens: int = 500
    ) -> Tuple[bool, float, str]:
        """
        Calculates if the credential has capacity right now.
        Returns:
            (has_capacity, required_wait_seconds, reason)
        """
        now = time.time()
        rpm = cred.effective_rpm
        tpm = cred.effective_tpm
        rpd = cred.effective_rpd

        # 1. Check RPD (Daily Limit)
        daily_count = self.get_24h_request_count(cred.id)
        if daily_count >= rpd:
            return False, 3600.0, f"Daily limit (RPD) reached ({daily_count}/{rpd} requests)"

        # 2. Clean sliding window
        window = self._clean_sliding_window(cred.id, now)
        current_reqs = len(window)
        current_tokens = sum(tokens for _, tokens in window)

        wait_time = 0.0
        reasons = []

        # 3. Check Minimum Inter-Request Pacing: spacing = (60.0 / rpm) + 0.05
        min_pacing = (60.0 / float(rpm)) + 0.05
        last_req = self._last_request_time.get(cred.id, 0.0)
        time_since_last = now - last_req
        if time_since_last < min_pacing:
            pacing_wait = min_pacing - time_since_last
            if pacing_wait > wait_time:
                wait_time = pacing_wait
                reasons.append(f"inter-request pacing ({min_pacing:.2f}s interval for {rpm} RPM)")

        # 4. Check RPM Sliding Window Limit
        if current_reqs >= rpm and window:
            oldest_ts = window[0][0]
            rpm_wait = max(0.0, 60.0 - (now - oldest_ts) + 0.05)
            if rpm_wait > wait_time:
                wait_time = rpm_wait
                reasons.append(f"RPM limit ({current_reqs}/{rpm} in last 60s)")

        # 5. Check TPM Sliding Window Limit
        if (current_tokens + estimated_tokens) > tpm and window:
            # Calculate how much time until enough tokens drop out of the 60s window
            needed_reduction = (current_tokens + estimated_tokens) - tpm
            accumulated = 0
            tpm_wait = 0.0
            for ts, tok in window:
                accumulated += tok
                if accumulated >= needed_reduction:
                    tpm_wait = max(0.0, 60.0 - (now - ts) + 0.05)
                    break
            if tpm_wait > wait_time:
                wait_time = tpm_wait
                reasons.append(f"TPM limit ({current_tokens + estimated_tokens:,}/{tpm:,} in last 60s)")

        if wait_time > 0.0:
            reason_str = ", ".join(reasons)
            return False, wait_time, reason_str

        return True, 0.0, "Capacity available"

    async def acquire(
        self,
        cred: ProviderCredentialMetadata,
        estimated_tokens: int = 500,
        max_wait_seconds: float = 65.0,
    ) -> bool:
        """
        Acquires permission to send a request, waiting proactively if needed to stay strictly
        under RPM, TPM, and RPD limits.
        """
        lock = self._get_lock(cred.id)
        async with lock:
            total_waited = 0.0
            while total_waited <= max_wait_seconds:
                can_go, wait_s, reason = self.check_capacity(cred, estimated_tokens)
                if can_go:
                    now = time.time()
                    self._last_request_time[cred.id] = now
                    # Record placeholder into sliding window
                    window = self._clean_sliding_window(cred.id, now)
                    window.append((now, estimated_tokens))
                    return True

                if wait_s > max_wait_seconds:
                    logger.warning(
                        f"Credential '{cred.name}' ({cred.provider.value}) rate limit blocked: {reason} (needs {wait_s:.1f}s wait > {max_wait_seconds}s)."
                    )
                    return False

                logger.info(
                    f"Pacing '{cred.name}' ({cred.provider.value}): sleeping {wait_s:.2f}s to respect {reason}..."
                )
                await asyncio.sleep(wait_s)
                total_waited += wait_s

            return False

    def record_usage(self, cred: ProviderCredentialMetadata, actual_tokens: int) -> None:
        """Updates the sliding window with exact tokens returned by the API."""
        now = time.time()
        self._last_request_time[cred.id] = now
        window = self._clean_sliding_window(cred.id, now)
        if window:
            # Replace latest entry's estimated token count with actual tokens
            ts, _ = window.pop()
            window.append((ts, actual_tokens))
        else:
            window.append((now, actual_tokens))

        # Invalidate daily count cache
        if cred.id in self._daily_counts:
            cached_at, count = self._daily_counts[cred.id]
            self._daily_counts[cred.id] = (cached_at, count + 1)


# Global rate limiter singleton
rate_limiter = RateLimiter()
