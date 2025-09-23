import os
from celery import Celery
from kombu import Queue

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Configure task queues for better organization and reliability
app.conf.task_routes = {
    'core.tasks.sync_player_data': {'queue': 'player_sync'},
    'core.tasks.sync_match_data_atomic': {'queue': 'match_processing'},
    'core.tasks.sync_match_timeline_atomic': {'queue': 'timeline_processing'},
    'core.tasks.recover_player_data': {'queue': 'recovery'},
    'core.tasks.cleanup_old_data': {'queue': 'maintenance'},
}

# Define queues with durability settings
app.conf.task_queues = (
    Queue('default', routing_key='default'),
    Queue('player_sync', routing_key='player_sync'),
    Queue('match_processing', routing_key='match_processing'),
    Queue('timeline_processing', routing_key='timeline_processing'),
    Queue('recovery', routing_key='recovery'),
    Queue('maintenance', routing_key='maintenance'),
)

# Configure task execution settings for better reliability
app.conf.task_defaults = {
    'queue': 'default',
    'exchange': 'default',
    'exchange_type': 'direct',
    'routing_key': 'default',
    'delivery_mode': 2,  # Make tasks persistent
    'priority': 5,  # Default priority
}

# Configure task retry settings
app.conf.task_annotations = {
    'core.tasks.sync_player_data': {'rate_limit': '10/m'},  # 10 tasks per minute
    'core.tasks.sync_match_data_atomic': {'rate_limit': '30/m'},  # 30 tasks per minute
    'core.tasks.sync_match_timeline_atomic': {'rate_limit': '20/m'},  # 20 tasks per minute
    'core.tasks.recover_player_data': {'rate_limit': '5/m'},  # 5 tasks per minute
    'core.tasks.auto_retry_failed_matches': {'rate_limit': '1/m'},  # 1 task per minute
}

# Configure Celery Beat for scheduled tasks
from celery.schedules import crontab

app.conf.beat_schedule = {
    'auto-retry-failed-matches': {
        'task': 'core.tasks.auto_retry_failed_matches',
        'schedule': crontab(minute=0, hour='*/6'),  # Every 6 hours
    },
    'health-check': {
        'task': 'core.tasks.health_check',
        'schedule': crontab(minute=0, hour='*/1'),  # Every hour
    },
}

# Load task modules from all registered Django apps.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')


# Configure signal handlers for better task management
from celery.signals import task_prerun, task_postrun, task_failure

@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, **kwds):
    """Log when a task starts."""
    print(f"Task {task.name}[{task_id}] starting with args={args}, kwargs={kwargs}")

@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **kwds):
    """Log when a task completes."""
    print(f"Task {task.name}[{task_id}] completed with state={state}")

@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwds):
    """Log when a task fails."""
    print(f"Task {sender.name}[{task_id}] failed: {exception}")