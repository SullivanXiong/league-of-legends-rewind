# Atomic Transactions and PlayerYearlyStats

This document describes the implementation of atomic transactions and the PlayerYearlyStats aggregation table for ensuring data consistency and providing fast aggregated queries.

## Overview

The system now includes:
1. **PlayerYearlyStats Model** - Aggregated yearly statistics for fast queries
2. **Atomic Transactions** - All-or-nothing data consistency per match
3. **Rsync-like Recovery** - Partial recovery and resume capabilities
4. **Progress Tracking** - Detailed progress updates for each operation

## PlayerYearlyStats Model

### Purpose
The `PlayerYearlyStats` model provides pre-calculated aggregated statistics for each player per year, eliminating the need to calculate sums and averages across multiple tables during queries.

### Fields

#### Basic Information
- `summoner` - Foreign key to Summoner
- `year` - Year of the statistics
- `platform` - Platform (na1, euw1, etc.)

#### Match Counts
- `total_matches` - Total number of matches played
- `wins` - Number of wins
- `losses` - Number of losses

#### Aggregated Stats
- `total_kills` - Sum of all kills
- `total_deaths` - Sum of all deaths
- `total_assists` - Sum of all assists
- `total_gold_earned` - Sum of gold earned
- `total_minions_killed` - Sum of minions killed
- `total_neutral_minions_killed` - Sum of neutral minions killed
- `total_damage_to_champions` - Sum of damage dealt to champions

#### Diversity Stats
- `unique_champions_played` - Number of unique champions played
- `most_played_champion` - Most frequently played champion
- `most_played_champion_count` - Count of most played champion
- `unique_roles_played` - Number of unique roles played
- `unique_lanes_played` - Number of unique lanes played

#### Calculated Fields
- `win_rate` - Win percentage
- `kda_ratio` - KDA ratio (Kills + Assists) / Deaths
- `average_kills` - Average kills per match
- `average_deaths` - Average deaths per match
- `average_assists` - Average assists per match
- `average_gold_per_match` - Average gold per match
- `average_cs_per_match` - Average CS per match

## Atomic Transactions

### Implementation
All data ingestion is now wrapped in `transaction.atomic()` blocks to ensure all-or-nothing consistency:

```python
@shared_task(bind=True)
def sync_match_data_atomic(self, match_id: str, platform: str, routing: str, puuid: str, year: int):
    try:
        with transaction.atomic():
            # All database operations for this match
            # If any operation fails, all changes are rolled back
    except Exception as e:
        # Return failure status instead of raising
        return {'success': False, 'error': str(e)}
```

### Benefits
1. **Data Consistency** - Either all data for a match is saved or none
2. **Partial Recovery** - Failed matches don't affect successful ones
3. **Resume Capability** - Can restart from where it left off

## Rsync-like Recovery

### Recovery Task
The `recover_player_data` task implements rsync-like functionality:

1. **Analysis Phase** - Checks what data already exists
2. **Missing Data Detection** - Identifies missing matches and timelines
3. **Selective Processing** - Only processes missing data
4. **Progress Tracking** - Provides detailed progress updates

### Recovery Endpoint
```http
POST /api/summoners/recover-data/
{
  "game_name": "PlayerName",
  "tag_line": "NA1",
  "platform": "na1",
  "routing": "americas",
  "year": 2025
}
```

### Recovery Response
```json
{
  "task_id": "uuid-task-id",
  "status": "started",
  "message": "Data recovery started for PlayerName#NA1",
  "recovery_mode": true,
  "platform": "na1",
  "routing": "americas",
  "year": 2025
}
```

## Aggregation Logic

### PlayerYearlyStatsAggregator Class

The `PlayerYearlyStatsAggregator` class handles all aggregation logic:

#### Methods
- `get_or_create_stats()` - Get or create yearly stats record
- `calculate_stats_from_matches()` - Calculate stats from match participants
- `update_stats()` - Update stats atomically
- `increment_stats()` - Incrementally update stats for new matches

#### Usage
```python
# Create aggregator for a summoner and year
aggregator = PlayerYearlyStatsAggregator(summoner, 2025)

# Update stats from all matches
stats = aggregator.update_stats()

# Incrementally update for a new match
aggregator.increment_stats(participant)
```

### Automatic Aggregation
Stats are automatically updated in two ways:

1. **Incremental Updates** - When new matches are processed
2. **Full Recalculation** - When updating yearly stats

## Progress Tracking

### Enhanced Progress Updates
Tasks now provide detailed progress information:

```json
{
  "task_id": "uuid-task-id",
  "status": "PROGRESS",
  "step": "processing_matches",
  "progress": 75,
  "total_matches": 20,
  "existing_matches": 5,
  "missing_matches": 15,
  "processed": 10,
  "failed": 2,
  "current_match": "NA1_1234567890"
}
```

### Progress Steps
1. `fetching_summoner` - Getting summoner information
2. `fetching_matches` - Retrieving match IDs from API
3. `processing_matches` - Processing individual matches
4. `updating_stats` - Updating yearly statistics
5. `completed` - Task finished

## API Endpoints

### New Endpoints

#### Data Recovery
```http
POST /api/summoners/recover-data/
```
Rsync-like recovery that only processes missing data.

#### Enhanced Task Status
```http
GET /api/summoners/task-status/?task_id=uuid-task-id
```
Returns detailed progress information including recovery statistics.

### Enhanced Responses

#### Summoner with Yearly Stats
```json
{
  "id": 123,
  "name": "PlayerName",
  "tag_line": "NA1",
  "platform": "na1",
  "yearly_stats": [
    {
      "year": 2025,
      "total_matches": 50,
      "wins": 30,
      "losses": 20,
      "win_rate": 60.0,
      "kda_ratio": 2.5,
      "average_kills": 8.5,
      "average_deaths": 4.2,
      "average_assists": 6.8
    }
  ]
}
```

## Data Consistency Guarantees

### Transaction Boundaries
- **Per Match** - Each match is processed in its own transaction
- **Per Timeline** - Timeline data is processed atomically
- **Per Stats Update** - Yearly stats updates are atomic

### Failure Handling
- **Match Failures** - Individual match failures don't affect others
- **Timeline Failures** - Timeline failures don't affect match data
- **Stats Failures** - Stats calculation failures are logged but don't stop processing

### Recovery Mechanisms
- **Automatic Retry** - Failed matches can be retried individually
- **Resume Capability** - Recovery tasks can resume from where they left off
- **Data Validation** - Existing data is validated before processing

## Performance Benefits

### Query Performance
- **Fast Aggregations** - Pre-calculated stats eliminate complex queries
- **Indexed Fields** - Key fields are indexed for fast lookups
- **Reduced Joins** - Single table queries instead of complex joins

### Processing Efficiency
- **Incremental Updates** - Only new data is processed
- **Selective Processing** - Only missing data is fetched from API
- **Batch Operations** - Multiple operations in single transactions

## Monitoring and Debugging

### Logging
Comprehensive logging for all operations:
- Match processing status
- Aggregation calculations
- Transaction success/failure
- Recovery progress

### Admin Interface
Enhanced Django admin with:
- Yearly stats overview
- Detailed field organization
- Search and filtering capabilities
- Read-only calculated fields

## Usage Examples

### Starting Data Sync
```bash
curl -X POST http://localhost:8000/api/summoners/sync-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "game_name": "PlayerName",
    "tag_line": "NA1",
    "platform": "na1",
    "routing": "americas",
    "year": 2025
  }'
```

### Recovery After Failure
```bash
curl -X POST http://localhost:8000/api/summoners/recover-data/ \
  -H "Content-Type: application/json" \
  -d '{
    "game_name": "PlayerName",
    "tag_line": "NA1",
    "platform": "na1",
    "routing": "americas",
    "year": 2025
  }'
```

### Checking Progress
```bash
curl "http://localhost:8000/api/summoners/task-status/?task_id=your-task-id"
```

### Querying Aggregated Data
```python
# Get yearly stats for a player
stats = PlayerYearlyStats.objects.filter(
    summoner__name="PlayerName",
    year=2025
).first()

print(f"Win rate: {stats.win_rate}%")
print(f"Average KDA: {stats.kda_ratio}")
print(f"Most played champion: {stats.most_played_champion}")
```

## Benefits Summary

1. **Data Consistency** - Atomic transactions ensure all-or-nothing data integrity
2. **Fast Queries** - Pre-calculated aggregations eliminate complex queries
3. **Recovery Capability** - Rsync-like recovery for partial failures
4. **Progress Tracking** - Detailed progress updates for monitoring
5. **Scalability** - Incremental processing and selective updates
6. **Reliability** - Comprehensive error handling and logging
7. **Performance** - Optimized database queries and indexing