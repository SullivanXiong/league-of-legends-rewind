# RabbitMQ Integration with Celery and Django

This document describes the integration of RabbitMQ as the message broker for Celery, providing better persistence, reliability, and task recovery capabilities.

## Overview

RabbitMQ has been integrated to replace Redis as the Celery message broker, providing:
- **Message Persistence** - Tasks survive broker restarts and crashes
- **Better Reliability** - Durable queues and exchanges
- **Task Recovery** - Automatic requeue on worker failures
- **Queue Management** - Organized task routing with dedicated queues
- **Monitoring** - Web-based management interface

## Architecture Changes

### Before (Redis)
```
Django → Redis → Celery Workers
```

### After (RabbitMQ)
```
Django → RabbitMQ → Celery Workers
     ↓
Management UI (Port 15672)
```

## RabbitMQ Configuration

### Docker Compose Setup
```yaml
rabbitmq:
  image: rabbitmq:3-management-alpine
  ports:
    - "5672:5672"    # AMQP port
    - "15672:15672"  # Management UI port
  environment:
    - RABBITMQ_DEFAULT_USER=guest
    - RABBITMQ_DEFAULT_PASS=guest
    - RABBITMQ_DEFAULT_VHOST=/
  volumes:
    - rabbitmq_data:/var/lib/rabbitmq
    - ./server/rabbitmq.conf:/etc/rabbitmq/rabbitmq.conf:ro
    - ./server/rabbitmq-definitions.json:/etc/rabbitmq/definitions.json:ro
  restart: unless-stopped
```

### Key Configuration Files

#### rabbitmq.conf
- **Persistence**: Enabled for message durability
- **Memory Management**: 60% memory watermark
- **Disk Limits**: 2GB free space requirement
- **Logging**: Console and file logging enabled
- **Heartbeat**: 60-second heartbeat interval

#### rabbitmq-definitions.json
- **Pre-configured Queues**: All task queues created on startup
- **Durable Exchanges**: All exchanges marked as durable
- **Message TTL**: Different TTL for different queue types
- **Dead Letter Exchanges**: Failed messages routed to default queue

## Queue Organization

### Task Queues
1. **default** - General tasks
2. **player_sync** - Player data synchronization
3. **match_processing** - Individual match processing
4. **timeline_processing** - Timeline data processing
5. **recovery** - Data recovery tasks
6. **maintenance** - Cleanup and maintenance tasks

### Queue Characteristics
```json
{
  "player_sync": {
    "ttl": "2 hours",
    "max_length": 1000,
    "rate_limit": "10/m"
  },
  "match_processing": {
    "ttl": "30 minutes",
    "max_length": 5000,
    "rate_limit": "30/m"
  },
  "timeline_processing": {
    "ttl": "30 minutes",
    "max_length": 5000,
    "rate_limit": "20/m"
  },
  "recovery": {
    "ttl": "4 hours",
    "max_length": 100,
    "rate_limit": "5/m"
  }
}
```

## Celery Configuration

### Settings Updates
```python
# RabbitMQ Configuration
CELERY_BROKER_URL = 'amqp://guest:guest@rabbitmq:5672//'
CELERY_RESULT_BACKEND = 'rpc://'

# Reliability Settings
CELERY_TASK_ACKS_LATE = True  # Acknowledge only after completion
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # Process one task at a time
CELERY_TASK_REJECT_ON_WORKER_LOST = True  # Reject tasks if worker lost

# Connection Settings
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_CONNECTION_RETRY = True
CELERY_BROKER_CONNECTION_MAX_RETRIES = 10
```

### Task Configuration
```python
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True
)
def sync_player_data(self, game_name: str, tag_line: str, ...):
    # Task implementation
```

## Task Reliability Features

### Automatic Retry
- **Exponential Backoff**: Retry delays increase exponentially
- **Jitter**: Random delay variation to prevent thundering herd
- **Max Retries**: Configurable per task type
- **Retry Reasons**: Automatic retry on exceptions

### Task Persistence
- **Durable Queues**: Queues survive broker restarts
- **Persistent Messages**: Messages written to disk
- **Delivery Mode**: Messages marked as persistent
- **Acknowledgment**: Late acknowledgment for reliability

### Failure Handling
- **Dead Letter Queues**: Failed messages routed to default queue
- **Worker Loss Detection**: Tasks rejected if worker dies
- **Connection Recovery**: Automatic reconnection on broker restart
- **Message TTL**: Messages expire to prevent queue buildup

## Monitoring and Management

### RabbitMQ Management UI
Access at `http://localhost:15672`
- **Username**: guest
- **Password**: guest

### Key Metrics to Monitor
1. **Queue Length** - Number of pending tasks
2. **Message Rate** - Tasks per second
3. **Consumer Count** - Active workers
4. **Memory Usage** - Broker memory consumption
5. **Disk Usage** - Persistence storage usage

### Queue Monitoring
```bash
# Check queue status
curl -u guest:guest http://localhost:15672/api/queues

# Check message rates
curl -u guest:guest http://localhost:15672/api/overview
```

## Benefits of RabbitMQ Integration

### 1. **Message Persistence**
- Tasks survive broker crashes
- No data loss on restart
- Reliable message delivery

### 2. **Better Task Recovery**
- Automatic requeue on worker failure
- Tasks picked up by available workers
- No manual intervention required

### 3. **Queue Organization**
- Dedicated queues for different task types
- Better resource allocation
- Easier monitoring and debugging

### 4. **Scalability**
- Multiple workers per queue
- Load balancing across workers
- Easy horizontal scaling

### 5. **Monitoring**
- Web-based management interface
- Real-time metrics and statistics
- Queue and message inspection

## Migration from Redis

### Changes Made
1. **Docker Compose**: Replaced Redis with RabbitMQ
2. **Dependencies**: Updated requirements.txt
3. **Settings**: Updated Celery configuration
4. **Tasks**: Added retry and reliability settings
5. **Queues**: Organized tasks into dedicated queues

### Backward Compatibility
- All existing API endpoints remain unchanged
- Task signatures remain the same
- Progress tracking continues to work
- Recovery mechanisms enhanced

## Usage Examples

### Starting Services
```bash
# Start all services including RabbitMQ
docker-compose up -d

# Check RabbitMQ status
docker-compose logs rabbitmq

# Access management UI
open http://localhost:15672
```

### Monitoring Tasks
```bash
# Check queue status
curl -u guest:guest http://localhost:15672/api/queues/%2F/player_sync

# Monitor message rates
curl -u guest:guest http://localhost:15672/api/overview
```

### Task Management
```bash
# Start Celery worker for specific queue
celery -A config worker -l info -Q player_sync

# Start Celery worker for multiple queues
celery -A config worker -l info -Q player_sync,match_processing

# Start Celery beat scheduler
celery -A config beat -l info
```

## Troubleshooting

### Common Issues

#### 1. Connection Refused
```bash
# Check RabbitMQ is running
docker-compose ps rabbitmq

# Check logs
docker-compose logs rabbitmq
```

#### 2. Queue Not Found
```bash
# Check queue exists in management UI
# Or recreate using definitions file
```

#### 3. Task Stuck in Queue
```bash
# Check worker status
celery -A config inspect active

# Purge queue if needed
celery -A config purge
```

### Performance Tuning

#### Memory Usage
- Monitor memory watermark (60%)
- Increase if needed: `vm_memory_high_watermark.relative = 0.8`

#### Disk Usage
- Monitor disk free space
- Increase limit if needed: `disk_free_limit.absolute = 5GB`

#### Connection Limits
- Adjust if needed: `connection_max = 2000`
- Channel limits: `channel_max = 4000`

## Security Considerations

### Production Setup
1. **Change Default Credentials**
   ```yaml
   environment:
     - RABBITMQ_DEFAULT_USER=your_username
     - RABBITMQ_DEFAULT_PASS=your_secure_password
   ```

2. **Enable SSL/TLS**
   ```yaml
   ports:
     - "5671:5671"  # AMQPS port
   ```

3. **Network Security**
   - Use internal networks
   - Restrict management UI access
   - Enable firewall rules

### Access Control
- Create dedicated users for different services
- Use virtual hosts for isolation
- Implement proper permissions

## Future Enhancements

### Clustering
- Multi-node RabbitMQ cluster
- High availability setup
- Load distribution

### Advanced Features
- Message routing rules
- Priority queues
- Dead letter handling
- Message compression

### Monitoring Integration
- Prometheus metrics
- Grafana dashboards
- Alerting rules
- Health checks

## Summary

The RabbitMQ integration provides:
- **Reliability**: Message persistence and automatic recovery
- **Scalability**: Organized queues and load balancing
- **Monitoring**: Web-based management interface
- **Performance**: Optimized task processing
- **Maintainability**: Better debugging and troubleshooting

This setup ensures that tasks are never lost, workers can recover from failures, and the system can scale horizontally as needed.