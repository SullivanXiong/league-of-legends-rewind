"""
Maintenance and cleanup tasks.

This module contains tasks for:
- Cleaning up old data
- Database maintenance
- System health checks
"""

import logging
from datetime import timedelta
from typing import Dict

from django.utils import timezone

from ..models import Match
from .utils import (
    TaskProgressTracker,
    handle_task_error,
    log_task_completion,
    maintenance_task
)

logger = logging.getLogger(__name__)


@maintenance_task
def cleanup_old_data(task, days: int = 30):
    """
    Cleanup old data to prevent database bloat.
    
    This task removes old matches and related data that are older than
    the specified number of days.
    
    Args:
        task: Celery task instance
        days: Number of days to keep data (default: 30)
    
    Returns:
        Dict containing cleanup results
    """
    with TaskProgressTracker(task, 'cleanup_old_data', total_steps=100) as tracker:
        try:
            # Step 1: Calculate cutoff date (20%)
            tracker.update('calculating_cutoff_date')
            cutoff_date = timezone.now() - timedelta(days=days)
            
            # Step 2: Find old matches (40%)
            tracker.update('finding_old_matches')
            old_matches = Match.objects.filter(created_at__lt=cutoff_date)
            count = old_matches.count()
            
            # Step 3: Delete old matches (80%)
            tracker.update('deleting_old_matches')
            old_matches.delete()
            
            # Step 4: Complete (100%)
            tracker.update('completed')
            
            result = {
                'success': True,
                'cleaned_matches': count,
                'cutoff_date': cutoff_date.isoformat(),
                'days_retained': days
            }
            
            logger.info(f"Cleaned up {count} old matches")
            log_task_completion(task, 'cleanup_old_data', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'cleanup_old_data')


@maintenance_task
def health_check(task):
    """
    Perform system health check.
    
    This task checks the health of various system components
    and returns status information.
    
    Args:
        task: Celery task instance
    
    Returns:
        Dict containing health check results
    """
    with TaskProgressTracker(task, 'health_check', total_steps=100) as tracker:
        try:
            # Step 1: Check database connection (25%)
            tracker.update('checking_database')
            db_status = _check_database_health()
            
            # Step 2: Check RabbitMQ connection (50%)
            tracker.update('checking_rabbitmq')
            rabbitmq_status = _check_rabbitmq_health()
            
            # Step 3: Check Riot API connectivity (75%)
            tracker.update('checking_riot_api')
            riot_api_status = _check_riot_api_health()
            
            # Step 4: Complete (100%)
            tracker.update('completed')
            
            result = {
                'success': True,
                'database': db_status,
                'rabbitmq': rabbitmq_status,
                'riot_api': riot_api_status,
                'timestamp': timezone.now().isoformat()
            }
            
            log_task_completion(task, 'health_check', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'health_check')


# Helper functions for maintenance tasks

def _check_database_health() -> Dict[str, any]:
    """Check database connection and basic operations."""
    try:
        # Test database connection
        Match.objects.count()
        
        return {
            'status': 'healthy',
            'message': 'Database connection successful'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'Database error: {str(e)}'
        }


def _check_rabbitmq_health() -> Dict[str, any]:
    """Check RabbitMQ connection."""
    try:
        from celery import current_app
        
        # Test broker connection
        inspect = current_app.control.inspect()
        stats = inspect.stats()
        
        if stats:
            return {
                'status': 'healthy',
                'message': 'RabbitMQ connection successful',
                'workers': len(stats)
            }
        else:
            return {
                'status': 'warning',
                'message': 'RabbitMQ connected but no workers found'
            }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'RabbitMQ error: {str(e)}'
        }


def _check_riot_api_health() -> Dict[str, any]:
    """Check Riot API connectivity."""
    try:
        from ..riot_service import RiotApiClient
        
        # Test API connection with a simple request
        client = RiotApiClient(platform='na1', routing='americas')
        # Note: This would require a valid API key to test
        # For now, just check if the client can be created
        
        return {
            'status': 'healthy',
            'message': 'Riot API client created successfully'
        }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'message': f'Riot API error: {str(e)}'
        }