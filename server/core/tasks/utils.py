"""
Common task utilities and decorators.

This module provides shared functionality for all Celery tasks including:
- Task decorators with retry logic
- Progress tracking utilities
- Error handling helpers
- Logging utilities
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, Optional, Type, Union

from celery import shared_task
from celery.exceptions import Retry

logger = logging.getLogger(__name__)


class TaskRetryConfig:
    """Configuration for task retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        countdown: int = 60,
        backoff: bool = True,
        backoff_max: int = 600,
        jitter: bool = True,
        autoretry_for: tuple = (Exception,)
    ):
        self.max_retries = max_retries
        self.countdown = countdown
        self.backoff = backoff
        self.backoff_max = backoff_max
        self.jitter = jitter
        self.autoretry_for = autoretry_for


def reliable_task(
    retry_config: Optional[TaskRetryConfig] = None,
    queue: Optional[str] = None,
    rate_limit: Optional[str] = None
):
    """
    Decorator for creating reliable Celery tasks with retry logic.
    
    Args:
        retry_config: TaskRetryConfig instance for retry behavior
        queue: Queue name for task routing
        rate_limit: Rate limit string (e.g., '10/m')
    
    Returns:
        Decorated task function
    """
    def decorator(func: Callable) -> Callable:
        # Default retry configuration
        config = retry_config or TaskRetryConfig()
        
        # Create the shared task with retry settings
        task = shared_task(
            bind=True,
            autoretry_for=config.autoretry_for,
            retry_kwargs={
                'max_retries': config.max_retries,
                'countdown': config.countdown
            },
            retry_backoff=config.backoff,
            retry_backoff_max=config.backoff_max,
            retry_jitter=config.jitter
        )(func)
        
        # Add queue routing if specified
        if queue:
            task.queue = queue
            
        # Add rate limiting if specified
        if rate_limit:
            task.rate_limit = rate_limit
            
        return task
    
    return decorator


def update_task_progress(task, step: str, progress: int, **kwargs):
    """
    Update task progress with standardized format.
    
    Args:
        task: Celery task instance
        step: Current step description
        progress: Progress percentage (0-100)
        **kwargs: Additional metadata to include
    """
    meta = {
        'step': step,
        'progress': progress,
        **kwargs
    }
    task.update_state(state='PROGRESS', meta=meta)
    logger.info(f"Task {task.request.id}: {step} - {progress}%")


def log_task_start(task, task_name: str, **kwargs):
    """Log task start with context."""
    logger.info(f"Starting {task_name}[{task.request.id}] with args={kwargs}")


def log_task_completion(task, task_name: str, result: Any = None):
    """Log task completion with result."""
    logger.info(f"Completed {task_name}[{task.request.id}] with result={result}")


def log_task_failure(task, task_name: str, error: Exception):
    """Log task failure with error details."""
    logger.error(f"Failed {task_name}[{task.request.id}]: {str(error)}")


def handle_task_error(task, error: Exception, task_name: str) -> Dict[str, Any]:
    """
    Standardized error handling for tasks.
    
    Args:
        task: Celery task instance
        error: Exception that occurred
        task_name: Name of the task for logging
    
    Returns:
        Error response dictionary
    """
    log_task_failure(task, task_name, error)
    task.update_state(state='FAILURE', meta={'error': str(error)})
    
    return {
        'success': False,
        'error': str(error),
        'task_id': task.request.id
    }


class TaskProgressTracker:
    """Context manager for tracking task progress."""
    
    def __init__(self, task, task_name: str, total_steps: int = 100):
        self.task = task
        self.task_name = task_name
        self.total_steps = total_steps
        self.current_step = 0
        
    def __enter__(self):
        log_task_start(self.task, self.task_name)
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            log_task_completion(self.task, self.task_name)
        else:
            log_task_failure(self.task, self.task_name, exc_val)
            
    def update(self, step: str, **kwargs):
        """Update progress with current step."""
        self.current_step += 1
        progress = int((self.current_step / self.total_steps) * 100)
        update_task_progress(self.task, step, progress, **kwargs)


# Predefined retry configurations for common task types
PLAYER_SYNC_RETRY = TaskRetryConfig(
    max_retries=3,
    countdown=60,
    backoff=True,
    backoff_max=600,
    jitter=True
)

MATCH_PROCESSING_RETRY = TaskRetryConfig(
    max_retries=5,
    countdown=30,
    backoff=True,
    backoff_max=300,
    jitter=True
)

TIMELINE_PROCESSING_RETRY = TaskRetryConfig(
    max_retries=3,
    countdown=20,
    backoff=True,
    backoff_max=180,
    jitter=True
)

RECOVERY_RETRY = TaskRetryConfig(
    max_retries=2,
    countdown=120,
    backoff=True,
    backoff_max=600,
    jitter=True
)


# Task decorators with predefined configurations
def player_sync_task(func: Callable) -> Callable:
    """Decorator for player synchronization tasks."""
    return reliable_task(
        retry_config=PLAYER_SYNC_RETRY,
        queue='player_sync',
        rate_limit='10/m'
    )(func)


def match_processing_task(func: Callable) -> Callable:
    """Decorator for match processing tasks."""
    return reliable_task(
        retry_config=MATCH_PROCESSING_RETRY,
        queue='match_processing',
        rate_limit='30/m'
    )(func)


def timeline_processing_task(func: Callable) -> Callable:
    """Decorator for timeline processing tasks."""
    return reliable_task(
        retry_config=TIMELINE_PROCESSING_RETRY,
        queue='timeline_processing',
        rate_limit='20/m'
    )(func)


def recovery_task(func: Callable) -> Callable:
    """Decorator for recovery tasks."""
    return reliable_task(
        retry_config=RECOVERY_RETRY,
        queue='recovery',
        rate_limit='5/m'
    )(func)


def maintenance_task(func: Callable) -> Callable:
    """Decorator for maintenance tasks."""
    return reliable_task(
        retry_config=TaskRetryConfig(max_retries=1, countdown=300),
        queue='maintenance',
        rate_limit='1/h'
    )(func)