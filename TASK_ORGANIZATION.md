# Task Organization and Structure

This document describes the reorganized Celery task structure for better maintainability, readability, and organization.

## Overview

The tasks have been reorganized from a single monolithic `tasks.py` file into a well-structured package with separate modules for different concerns. This makes the codebase much easier to understand, maintain, and extend.

## New Structure

```
core/
└── tasks/
    ├── __init__.py          # Task package initialization and exports
    ├── utils.py             # Common utilities and decorators
    ├── player_tasks.py      # Player data synchronization tasks
    ├── match_tasks.py       # Individual match processing tasks
    ├── timeline_tasks.py    # Timeline data processing tasks
    └── maintenance_tasks.py # Cleanup and maintenance tasks
```

## Module Organization

### 1. `tasks/utils.py` - Common Utilities

**Purpose**: Shared functionality for all Celery tasks

**Key Components**:
- **TaskRetryConfig**: Configuration class for retry behavior
- **reliable_task**: Decorator for creating reliable tasks with retry logic
- **TaskProgressTracker**: Context manager for progress tracking
- **Error Handling**: Standardized error handling functions
- **Logging Utilities**: Task lifecycle logging functions
- **Predefined Decorators**: Ready-to-use decorators for different task types

**Example Usage**:
```python
from .utils import player_sync_task, TaskProgressTracker

@player_sync_task
def sync_player_data(task, game_name: str, tag_line: str):
    with TaskProgressTracker(task, 'sync_player_data', total_steps=100) as tracker:
        tracker.update('fetching_summoner')
        # ... task logic
```

### 2. `tasks/player_tasks.py` - Player Data Synchronization

**Purpose**: High-level player data synchronization workflows

**Key Tasks**:
- `sync_player_data`: Main player sync orchestration
- `recover_player_data`: Rsync-like recovery functionality

**Features**:
- Comprehensive progress tracking
- Rsync-like recovery analysis
- Atomic transaction management
- Detailed error handling and logging

**Example**:
```python
# Start player data sync
task = sync_player_data.delay(
    game_name="PlayerName",
    tag_line="NA1",
    platform="na1",
    routing="americas",
    year=2025
)
```

### 3. `tasks/match_tasks.py` - Individual Match Processing

**Purpose**: Processing individual match data atomically

**Key Tasks**:
- `sync_match_data_atomic`: Atomic match data processing

**Features**:
- All-or-nothing transaction consistency
- Participant processing
- Incremental yearly stats updates
- Timeline sync coordination

**Example**:
```python
# Process individual match
result = sync_match_data_atomic.delay(
    match_id="NA1_1234567890",
    platform="na1",
    routing="americas",
    puuid="player_puuid",
    year=2025
)
```

### 4. `tasks/timeline_tasks.py` - Timeline Data Processing

**Purpose**: Processing match timeline data

**Key Tasks**:
- `sync_match_timeline_atomic`: Atomic timeline processing

**Features**:
- Timeline data validation
- Duplicate detection
- Atomic timeline creation
- Error handling for timeline-specific issues

**Example**:
```python
# Sync timeline data
result = sync_match_timeline_atomic.delay(
    match_id="NA1_1234567890",
    platform="na1",
    routing="americas"
)
```

### 5. `tasks/maintenance_tasks.py` - System Maintenance

**Purpose**: Cleanup and maintenance operations

**Key Tasks**:
- `cleanup_old_data`: Remove old data to prevent bloat
- `health_check`: System health monitoring

**Features**:
- Configurable cleanup periods
- System health monitoring
- Database and broker health checks
- Maintenance operation logging

**Example**:
```python
# Cleanup old data
result = cleanup_old_data.delay(days=30)

# Check system health
result = health_check.delay()
```

## Task Decorators and Configuration

### Predefined Task Decorators

Each task type has a predefined decorator with appropriate retry and rate limiting:

```python
@player_sync_task      # 10/m rate limit, 3 retries
@match_processing_task # 30/m rate limit, 5 retries  
@timeline_processing_task # 20/m rate limit, 3 retries
@recovery_task         # 5/m rate limit, 2 retries
@maintenance_task      # 1/h rate limit, 1 retry
```

### Retry Configuration

```python
PLAYER_SYNC_RETRY = TaskRetryConfig(
    max_retries=3,
    countdown=60,
    backoff=True,
    backoff_max=600,
    jitter=True
)
```

## Progress Tracking

### TaskProgressTracker Context Manager

```python
with TaskProgressTracker(task, 'task_name', total_steps=100) as tracker:
    tracker.update('step_name', additional_data='value')
    # Automatic logging and progress updates
```

### Manual Progress Updates

```python
update_task_progress(task, 'processing_matches', 75, 
                    processed=15, failed=2, current_match='NA1_123')
```

## Error Handling

### Standardized Error Responses

```python
def handle_task_error(task, error: Exception, task_name: str) -> Dict[str, Any]:
    return {
        'success': False,
        'error': str(error),
        'task_id': task.request.id
    }
```

### Task Lifecycle Logging

```python
log_task_start(task, 'sync_player_data', game_name='PlayerName')
log_task_completion(task, 'sync_player_data', result)
log_task_failure(task, 'sync_player_data', error)
```

## Benefits of New Organization

### 1. **Improved Readability**
- Each module has a single responsibility
- Clear separation of concerns
- Easy to understand task flow

### 2. **Better Maintainability**
- Changes to one task type don't affect others
- Easier to add new tasks
- Clear module boundaries

### 3. **Enhanced Reusability**
- Common utilities shared across tasks
- Consistent patterns and decorators
- Standardized error handling

### 4. **Easier Testing**
- Individual modules can be tested separately
- Mock utilities for testing
- Clear task boundaries

### 5. **Better Documentation**
- Comprehensive docstrings
- Type hints throughout
- Clear examples and usage patterns

## Migration Guide

### Import Style
```python
# Package-level import (recommended)
from core.tasks import sync_player_data

# Direct module import (also works)
from core.tasks.player_tasks import sync_player_data
```

### Clean Architecture

The old monolithic `tasks.py` file has been completely removed. All tasks are now organized in the clean, modular structure described above.

## Task Queue Organization

Tasks are automatically routed to appropriate queues:

- `player_sync` → Player synchronization tasks
- `match_processing` → Individual match processing
- `timeline_processing` → Timeline data processing
- `recovery` → Data recovery tasks
- `maintenance` → Cleanup and maintenance
- `default` → General tasks

## Monitoring and Debugging

### Task Status Monitoring

```python
# Check task status
from celery.result import AsyncResult
result = AsyncResult(task_id)
print(f"Status: {result.status}")
print(f"Progress: {result.info}")
```

### Logging

All tasks include comprehensive logging:
- Task start/completion/failure
- Progress updates
- Error details
- Performance metrics

### Queue Monitoring

```bash
# Monitor specific queue
celery -A config worker -l info -Q player_sync

# Monitor multiple queues
celery -A config worker -l info -Q player_sync,match_processing
```

## Best Practices

### 1. **Use Appropriate Decorators**
```python
@player_sync_task  # Not @shared_task
def sync_player_data(task, ...):
    pass
```

### 2. **Implement Progress Tracking**
```python
with TaskProgressTracker(task, 'task_name', total_steps=100) as tracker:
    tracker.update('step_name')
```

### 3. **Handle Errors Gracefully**
```python
try:
    # Task logic
except Exception as e:
    return handle_task_error(task, e, 'task_name')
```

### 4. **Use Type Hints**
```python
def sync_player_data(task, game_name: str, tag_line: str, platform: str = 'na1') -> Dict[str, Any]:
    pass
```

### 5. **Document Task Purpose**
```python
def sync_player_data(task, game_name: str, tag_line: str):
    """
    Sync all data for a player including summoner info, matches, and timelines.
    
    Args:
        task: Celery task instance
        game_name: Player's game name
        tag_line: Player's tag line
    
    Returns:
        Dict containing sync results and statistics
    """
```

## Future Enhancements

### Planned Improvements
1. **Task Metrics**: Performance monitoring and metrics collection
2. **Task Dependencies**: Task chaining and dependency management
3. **Batch Processing**: Efficient batch task processing
4. **Task Scheduling**: Dynamic task scheduling capabilities
5. **Health Monitoring**: Enhanced system health monitoring

### Extensibility
The new structure makes it easy to:
- Add new task types
- Implement custom retry strategies
- Add new monitoring capabilities
- Extend error handling
- Add performance optimizations

## Summary

The reorganized task structure provides:
- **Clear Organization**: Tasks grouped by functionality
- **Better Maintainability**: Easier to understand and modify
- **Enhanced Reliability**: Consistent error handling and retry logic
- **Improved Monitoring**: Better progress tracking and logging
- **Future-Proof Design**: Easy to extend and enhance

This organization makes the codebase much more professional and maintainable while preserving all existing functionality.