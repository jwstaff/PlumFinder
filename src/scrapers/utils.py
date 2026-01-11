"""
Scraper Utilities

Shared utilities for all scrapers:
- robots.txt compliance checking
- Exponential backoff for retries
- Response caching
"""

import time
import hashlib
import json
from typing import Optional, Callable, Any
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from functools import wraps
from datetime import datetime, timedelta


class RobotsChecker:
    """
    Checks robots.txt compliance for web scraping.
    Caches robots.txt files to avoid repeated fetches.
    """

    def __init__(self, user_agent: str = "*"):
        self.user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._fetch_times: dict[str, datetime] = {}
        self._cache_duration = timedelta(hours=24)

    def _get_robots_url(self, url: str) -> str:
        """Extract robots.txt URL from any URL."""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def _get_parser(self, url: str, client=None) -> Optional[RobotFileParser]:
        """Get or create a RobotFileParser for the given URL's domain."""
        robots_url = self._get_robots_url(url)
        domain = urlparse(url).netloc

        # Check if we have a cached parser that's still valid
        if domain in self._parsers:
            fetch_time = self._fetch_times.get(domain)
            if fetch_time and datetime.now() - fetch_time < self._cache_duration:
                return self._parsers[domain]

        # Fetch and parse robots.txt
        parser = RobotFileParser()
        parser.set_url(robots_url)

        try:
            if client:
                # Use provided HTTP client
                response = client.get(robots_url, timeout=10.0)
                if response.status_code == 200:
                    parser.parse(response.text.splitlines())
                else:
                    # No robots.txt or error - allow all
                    parser.parse([])
            else:
                # Use default reader
                parser.read()

            self._parsers[domain] = parser
            self._fetch_times[domain] = datetime.now()

        except Exception as e:
            # If we can't fetch robots.txt, assume allowed
            parser.parse([])
            self._parsers[domain] = parser
            self._fetch_times[domain] = datetime.now()

        return parser

    def can_fetch(self, url: str, client=None) -> bool:
        """
        Check if the given URL can be fetched according to robots.txt.

        Args:
            url: The URL to check
            client: Optional httpx client to use for fetching robots.txt

        Returns:
            True if fetching is allowed, False otherwise
        """
        try:
            parser = self._get_parser(url, client)
            if parser:
                return parser.can_fetch(self.user_agent, url)
        except Exception:
            pass

        # Default to allowing if we can't determine
        return True

    def get_crawl_delay(self, url: str) -> Optional[float]:
        """Get the crawl delay specified in robots.txt."""
        try:
            domain = urlparse(url).netloc
            parser = self._parsers.get(domain)
            if parser:
                delay = parser.crawl_delay(self.user_agent)
                return delay if delay else None
        except Exception:
            pass
        return None


class ResponseCache:
    """
    Simple in-memory cache for HTTP responses.
    Uses TTL-based expiration.
    """

    def __init__(self, default_ttl: int = 300):
        """
        Initialize cache.

        Args:
            default_ttl: Default time-to-live in seconds (default 5 minutes)
        """
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self.default_ttl = default_ttl

    def _make_key(self, url: str, params: Optional[dict] = None) -> str:
        """Create a cache key from URL and parameters."""
        key_data = url
        if params:
            key_data += json.dumps(params, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()

    def get(self, url: str, params: Optional[dict] = None) -> Optional[Any]:
        """
        Get a cached response.

        Args:
            url: The request URL
            params: Optional query parameters

        Returns:
            Cached data if available and not expired, None otherwise
        """
        key = self._make_key(url, params)

        if key in self._cache:
            data, expiry = self._cache[key]
            if datetime.now() < expiry:
                return data
            else:
                # Expired, remove it
                del self._cache[key]

        return None

    def set(self, url: str, data: Any, params: Optional[dict] = None, ttl: Optional[int] = None):
        """
        Cache a response.

        Args:
            url: The request URL
            data: The data to cache
            params: Optional query parameters
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        key = self._make_key(url, params)
        expiry = datetime.now() + timedelta(seconds=ttl or self.default_ttl)
        self._cache[key] = (data, expiry)

    def clear(self):
        """Clear all cached data."""
        self._cache.clear()

    def cleanup(self):
        """Remove expired entries."""
        now = datetime.now()
        expired_keys = [
            key for key, (_, expiry) in self._cache.items()
            if now >= expiry
        ]
        for key in expired_keys:
            del self._cache[key]


def with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    retryable_status_codes: tuple = (429, 500, 502, 503, 504),
):
    """
    Decorator that adds exponential backoff retry logic to a function.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exponential_base: Base for exponential calculation
        retryable_exceptions: Tuple of exceptions that should trigger a retry
        retryable_status_codes: HTTP status codes that should trigger a retry

    Usage:
        @with_exponential_backoff(max_retries=3, base_delay=1.0)
        def fetch_data(url):
            response = client.get(url)
            response.raise_for_status()
            return response.json()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)

                    # Check if result is an HTTP response with retryable status
                    if hasattr(result, 'status_code'):
                        if result.status_code in retryable_status_codes:
                            if attempt < max_retries:
                                delay = min(
                                    base_delay * (exponential_base ** attempt),
                                    max_delay
                                )
                                print(f"Got {result.status_code}, retrying in {delay:.1f}s...")
                                time.sleep(delay)
                                continue
                            else:
                                # Max retries reached, return the response anyway
                                return result

                    return result

                except retryable_exceptions as e:
                    last_exception = e

                    if attempt < max_retries:
                        delay = min(
                            base_delay * (exponential_base ** attempt),
                            max_delay
                        )
                        print(f"Request failed ({e}), retrying in {delay:.1f}s...")
                        time.sleep(delay)
                    else:
                        raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def retry_on_failure(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
):
    """
    Retry a function with exponential backoff.

    This is the functional (non-decorator) version for cases where
    you need more control over the retry logic.

    Args:
        func: Function to call (should take no arguments or use closure)
        max_retries: Maximum retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        The function's return value

    Raises:
        The last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_exception = e

            if attempt < max_retries:
                delay = min(base_delay * (2 ** attempt), max_delay)
                print(f"Attempt {attempt + 1} failed ({e}), retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                break

    if last_exception:
        raise last_exception


# Global instances for shared use
_robots_checker = None
_response_cache = None


def get_robots_checker(user_agent: str = "*") -> RobotsChecker:
    """Get or create a global RobotsChecker instance."""
    global _robots_checker
    if _robots_checker is None:
        _robots_checker = RobotsChecker(user_agent)
    return _robots_checker


def get_response_cache(ttl: int = 300) -> ResponseCache:
    """Get or create a global ResponseCache instance."""
    global _response_cache
    if _response_cache is None:
        _response_cache = ResponseCache(ttl)
    return _response_cache
