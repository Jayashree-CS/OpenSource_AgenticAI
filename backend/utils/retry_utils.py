"""
retry_utils.py

Utility functions for retry logic with exponential backoff.
Used across actions for resilient API calls and webhook deliveries.
"""

import time
import random
import logging
from typing import Callable, Any, Optional, Dict, Union
from functools import wraps
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategies for different types of operations."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_INTERVAL = "fixed_interval"


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: tuple = (Exception,),
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions
        self.strategy = strategy


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay for next retry attempt based on strategy."""
    if attempt <= 1:
        return config.base_delay
    
    if config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
        delay = config.base_delay * (config.backoff_multiplier ** (attempt - 1))
    elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
        delay = config.base_delay + (attempt - 1) * config.base_delay
    else:  # FIXED_INTERVAL
        delay = config.base_delay
    
    # Apply jitter if enabled
    if config.jitter:
        jitter_amount = delay * 0.1  # 10% jitter
        delay += random.uniform(-jitter_amount, jitter_amount)
    
    return min(delay, config.max_delay)


def is_retryable_exception(exception: Exception, config: RetryConfig) -> bool:
    """Check if exception should trigger a retry."""
    return isinstance(exception, config.retryable_exceptions)


def retry_with_backoff(
    config: Optional[RetryConfig] = None,
    default_config: Optional[RetryConfig] = None
):
    """
    Decorator for retrying functions with exponential backoff.
    
    Args:
        config: Retry configuration for this function
        default_config: Default configuration if config not provided
    
    Usage:
        @retry_with_backoff(max_attempts=3, base_delay=1.0)
        async def my_function():
            # Your function logic here
            pass
    """
    
    if config is None:
        config = default_config or RetryConfig()
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if this exception type should be retried
                    if not is_retryable_exception(e, config):
                        logger.error(f"Non-retryable exception in {func.__name__}: {e}")
                        raise e
                    
                    # Log retry attempt
                    delay = calculate_delay(attempt, config)
                    logger.warning(
                        f"Retry attempt {attempt}/{config.max_attempts} for {func.__name__} "
                        f"after {delay:.2f}s delay: {e}"
                    )
                    
                    # Wait before next attempt
                    await asyncio.sleep(delay)
            
            # All retries exhausted
            logger.error(
                f"All {config.max_attempts} retry attempts failed for {func.__name__}. "
                f"Last exception: {last_exception}"
            )
            raise last_exception
        
        return wrapper
    
    return decorator


async def retry_operation(
    operation: Callable,
    *args,
    config: Optional[RetryConfig] = None,
    default_config: Optional[RetryConfig] = None,
    **kwargs
) -> Any:
    """
    Execute an operation with retry logic.
    
    Args:
        operation: The async function to retry
        config: Retry configuration
        default_config: Default configuration if config not provided
        *args: Arguments to pass to operation
        **kwargs: Keyword arguments to pass to operation
    
    Returns:
        Result of the operation or raises last exception
    """
    if config is None:
        config = default_config or RetryConfig()
    
    last_exception = None
    
    for attempt in range(1, config.max_attempts + 1):
        try:
            return await operation(*args, **kwargs)
            
        except Exception as e:
            last_exception = e
            
            # Check if this exception type should be retried
            if not is_retryable_exception(e, config):
                logger.error(f"Non-retryable exception: {e}")
                raise e
            
            # Log retry attempt
            delay = calculate_delay(attempt, config)
            logger.warning(
                f"Retry attempt {attempt}/{config.max_attempts} after {delay:.2f}s delay: {e}"
            )
            
            # Wait before next attempt
            await asyncio.sleep(delay)
    
    # All retries exhausted
    logger.error(
        f"All {config.max_attempts} retry attempts failed. Last exception: {last_exception}"
    )
    raise last_exception


class CircuitBreaker:
    """
    Simple circuit breaker pattern for preventing cascading failures.
    """
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def is_open(self) -> bool:
        return self.state == "OPEN"
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == "OPEN":
            return True
        
        if self.state == "HALF_OPEN":
            # Allow some operations in half-open state
            return True
        
        if self.state == "CLOSED":
            # Check if recovery timeout has passed
            if (self.last_failure_time and 
                time.time() - self.last_failure_time > self.recovery_timeout):
                self.state = "HALF_OPEN"
                self.failure_count = 0
                return True
        
        return False
    
    def record_success(self):
        """Record a successful operation."""
        self.failure_count = 0
        self.state = "OPEN"
        self.last_failure_time = None
    
    def record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "CLOSED"
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")


# Predefined retry configurations for common use cases
WEBHOOK_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    backoff_multiplier=2.0,
    jitter=True,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
        # Add specific HTTP/network exceptions as needed
    )
)

API_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.5,
    max_delay=5.0,
    backoff_multiplier=1.5,
    jitter=False,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
    )
)

LLM_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.2,
    max_delay=2.0,
    strategy=RetryStrategy.LINEAR_BACKOFF,
    jitter=False,
    retryable_exceptions=(
        TimeoutError,
        ConnectionError,
        OSError,
    )
)
