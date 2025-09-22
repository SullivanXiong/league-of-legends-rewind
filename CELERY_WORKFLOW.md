# Celery Player Data Sync Workflow

This document describes the new Celery-based workflow for syncing player data from the Riot Games League of Legends API.

## Overview

The workflow allows the frontend to make a single POST request with a player's `game_name` and `tag_line`, which then spawns Celery workers to handle the complete data digestion process. The workers will pull all matches from a configurable year (default: 2025).

## Architecture

### Components

1. **Django REST API** - Handles the initial request and returns task ID
2. **Celery Workers** - Process the data sync tasks asynchronously
3. **Redis** - Message broker and result backend for Celery
4. **PostgreSQL** - Database for storing all data

### Services

- `django-server` - Main Django application
- `celery-worker` - Processes background tasks
- `celery-beat` - Handles scheduled tasks
- `postgres` - Database
- `redis` - Message broker

## API Endpoints

### Start Player Data Sync

```http
POST /api/summoners/sync-data/
Content-Type: application/json

{
  "game_name": "PlayerName",
  "tag_line": "NA1",
  "platform": "na1",
  "routing": "americas",
  "year": 2025
}
```

**Response:**
```json
{
  "task_id": "uuid-task-id",
  "status": "started",
  "message": "Data sync started for PlayerName#NA1",
  "platform": "na1",
  "routing": "americas",
  "year": 2025
}
```

### Check Task Status

```http
GET /api/summoners/task-status/?task_id=uuid-task-id
```

**Response (In Progress):**
```json
{
  "task_id": "uuid-task-id",
  "status": "PROGRESS",
  "step": "processing_matches",
  "progress": 75,
  "processed": 15,
  "total": 20
}
```

**Response (Completed):**
```json
{
  "task_id": "uuid-task-id",
  "status": "SUCCESS",
  "summoner_id": 123,
  "summoner_name": "PlayerName",
  "processed_matches": 20,
  "total_matches": 20,
  "year": 2025
}
```

## Celery Tasks

### Main Task: `sync_player_data`

Orchestrates the entire data sync process:

1. **Fetch Summoner Info** - Gets or creates summoner record
2. **Get Match IDs** - Retrieves match IDs for the specified year
3. **Process Matches** - Spawns individual match sync tasks
4. **Update Progress** - Provides real-time progress updates

### Sub-tasks:

- `sync_match_data` - Syncs individual match data and participants
- `sync_match_timeline` - Syncs timeline data for matches
- `cleanup_old_data` - Optional cleanup task for old data

## Configuration

### Environment Variables

```bash
# Celery Configuration
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# Riot API Configuration
RIOT_API_KEY=your_riot_api_key
DEFAULT_MATCH_YEAR=2025
```

### Year Filtering

The system supports filtering matches by year:
- Default year: 2025 (configurable via `DEFAULT_MATCH_YEAR`)
- Can be overridden per request
- Uses timestamp filtering in Riot API calls

## Running the System

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f celery-worker
docker-compose logs -f django-server
```

### Manual Setup

```bash
# Start Redis
redis-server

# Start Celery Worker
celery -A config worker -l info

# Start Celery Beat (for scheduled tasks)
celery -A config beat -l info

# Start Django Server
python manage.py runserver
```

## Data Flow

1. **Frontend Request** → POST to `/api/summoners/sync-data/`
2. **Task Creation** → Celery task queued with Redis
3. **Worker Processing** → Background task processes data
4. **Progress Updates** → Real-time status via task status endpoint
5. **Data Storage** → All data stored in PostgreSQL
6. **Completion** → Final status returned

## Error Handling

- **API Errors** - Proper HTTP status codes and error messages
- **Task Failures** - Celery handles retries and failure states
- **Rate Limiting** - Built-in delays between API calls
- **Data Validation** - Input validation for all parameters

## Monitoring

- **Task Status** - Check progress via API endpoint
- **Celery Flower** - Optional web-based monitoring tool
- **Logs** - Comprehensive logging for debugging
- **Database** - All data persisted for analysis

## Benefits

1. **Asynchronous Processing** - Non-blocking API responses
2. **Scalability** - Multiple workers can process tasks in parallel
3. **Reliability** - Task retry mechanisms and error handling
4. **Progress Tracking** - Real-time updates on sync progress
5. **Configurable** - Year filtering and other parameters
6. **Efficient** - Only syncs new data, skips existing matches