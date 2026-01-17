import time
import logging
import threading
from collections import deque
import os
from datetime import datetime, timedelta
from typing import Optional, Callable, Any
import asyncio

logger = logging.getLogger(__name__)

class GeminiRateLimiter:
    """
    Rate limiter for Gemini API to handle per-minute rate limits.
    Implements sliding window with automatic backoff.
    """
    
    def __init__(self, requests_per_minute: int = 15, safety_margin: float = 0.8):
        """
        Initialize rate limiter.
        
        Args:
            requests_per_minute: Maximum requests per minute (default 15 for gemini-2.5-flash-lite)
            safety_margin: Safety factor to avoid hitting limits (0.8 = use 80% of limit)
        """
        self.requests_per_minute = requests_per_minute
        self.effective_limit = int(requests_per_minute * safety_margin)  # 12 requests with default
        self.request_timestamps = deque()
        self.lock = threading.Lock()
        
        logger.info(f"Initialized Gemini rate limiter: {self.effective_limit}/{requests_per_minute} RPM")
    
    def _cleanup_old_requests(self):
        """Remove request timestamps older than 1 minute."""
        current_time = time.time()
        minute_ago = current_time - 60
        
        while self.request_timestamps and self.request_timestamps[0] < minute_ago:
            self.request_timestamps.popleft()
    
    def _get_current_request_count(self) -> int:
        """Get current number of requests in the last minute."""
        self._cleanup_old_requests()
        return len(self.request_timestamps)
    
    def _calculate_wait_time(self) -> float:
        """Calculate how long to wait before making next request."""
        current_count = self._get_current_request_count()
        
        if current_count < self.effective_limit:
            return 0.0
        
        # If we're at the limit, wait until the oldest request expires
        if self.request_timestamps:
            oldest_request = self.request_timestamps[0]
            wait_time = 60 - (time.time() - oldest_request) + 1  # Add 1 second buffer
            return max(0.0, wait_time)
        
        return 60.0  # Fallback: wait a full minute
    
    def wait_if_needed(self):
        """Wait if necessary to respect rate limits."""
        with self.lock:
            wait_time = self._calculate_wait_time()
            
            if wait_time > 0:
                logger.warning(f"Rate limit approached. Waiting {wait_time:.1f} seconds...")
                time.sleep(wait_time)
            
            # Record this request
            self.request_timestamps.append(time.time())
            current_count = len(self.request_timestamps)
            
            logger.debug(f"Request recorded. Current count: {current_count}/{self.effective_limit}")
    
    def get_status(self) -> dict:
        """Get current rate limiter status for monitoring."""
        with self.lock:
            current_count = self._get_current_request_count()
            next_reset = None
            
            if self.request_timestamps:
                oldest_request = self.request_timestamps[0]
                next_reset = datetime.fromtimestamp(oldest_request + 60).isoformat()
            
            return {
                "current_requests": current_count,
                "limit": self.effective_limit,
                "max_limit": self.requests_per_minute,
                "next_reset": next_reset,
                "capacity_remaining": self.effective_limit - current_count
            }

# Global rate limiter instance
_gemini_rate_limiter = None

def get_gemini_rate_limiter() -> GeminiRateLimiter:
    """Get or create the global Gemini rate limiter instance."""
    global _gemini_rate_limiter
    if _gemini_rate_limiter is None:
        # Select limits based on environment / key tier
        env = os.getenv('DEPLOYMENT_ENV', '').lower()
        # Defaults per Gemini docs: free tier is lower; paid tier substantially higher
        # We'll use conservative defaults and can tune as needed
        if env == 'production':
            # Paid plan: allow higher RPM, e.g., 60 RPM with 80% safety -> 48
            _gemini_rate_limiter = GeminiRateLimiter(requests_per_minute=60, safety_margin=0.8)
        else:
            # Free plan: conservative limit 15 RPM with 80% safety -> 12
            _gemini_rate_limiter = GeminiRateLimiter(requests_per_minute=15, safety_margin=0.8)
    return _gemini_rate_limiter

def with_rate_limiting(func: Callable) -> Callable:
    """
    Decorator to add rate limiting to Gemini API calls.
    
    Usage:
        @with_rate_limiting
        def my_gemini_call():
            return client.models.generate_content(...)
    """
    def wrapper(*args, **kwargs):
        rate_limiter = get_gemini_rate_limiter()
        rate_limiter.wait_if_needed()
        
        try:
            result = func(*args, **kwargs)
            logger.debug("Gemini API call successful")
            return result
        except Exception as e:
            # Check if it's a rate limit error
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                logger.error(f"Rate limit error despite rate limiting: {e}")
                # Force a longer wait and retry once
                time.sleep(65)  # Wait just over a minute
                rate_limiter.wait_if_needed()
                return func(*args, **kwargs)
            else:
                raise
    
    return wrapper

def rate_limited_gemini_call(func: Callable, *args, max_retries: int = 3, **kwargs) -> Any:
    """
    Execute a Gemini API call with rate limiting and retry logic.
    
    Args:
        func: The function to call
        *args: Arguments to pass to func
        max_retries: Maximum number of retries on rate limit errors
        **kwargs: Keyword arguments to pass to func
    
    Returns:
        Result of the function call
    
    Raises:
        The last exception if all retries fail
    """
    rate_limiter = get_gemini_rate_limiter()
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            # Wait according to rate limiting
            rate_limiter.wait_if_needed()
            
            # Make the API call
            result = func(*args, **kwargs)
            
            if attempt > 0:
                logger.info(f"Gemini API call succeeded on attempt {attempt + 1}")
            
            return result
            
        except Exception as e:
            last_exception = e
            
            # Check if it's a rate limit error
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                if attempt < max_retries:
                    wait_time = (2 ** attempt) * 30  # Exponential backoff: 30s, 60s, 120s
                    logger.warning(f"Rate limit hit on attempt {attempt + 1}. Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"Rate limit error after {max_retries + 1} attempts: {e}")
            else:
                # Non-rate-limit error, don't retry
                logger.error(f"Non-rate-limit error in Gemini API call: {e}")
                break
    
    # If we get here, all retries failed
    raise last_exception 