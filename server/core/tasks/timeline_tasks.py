"""
Timeline data processing tasks.

This module contains tasks for:
- Syncing match timeline data atomically
- Processing frame-by-frame match data
- Managing timeline data consistency
"""

import logging
from typing import Dict

from django.db import transaction

from ..models import Match, MatchTimeline
from ..riot_service import RiotApiClient
from .utils import (
    TaskProgressTracker,
    handle_task_error,
    log_task_completion,
    timeline_processing_task
)

logger = logging.getLogger(__name__)


@timeline_processing_task
def sync_match_timeline_atomic(task, match_id: str, platform: str, routing: str):
    """
    Sync timeline data for a specific match atomically.
    
    This ensures timeline data is processed consistently and durably.
    
    Args:
        task: Celery task instance
        match_id: Riot match ID
        platform: Platform (na1, euw1, etc.)
        routing: Routing region (americas, europe, asia)
    
    Returns:
        Dict containing timeline sync results
    """
    with TaskProgressTracker(task, 'sync_match_timeline_atomic', total_steps=100) as tracker:
        try:
            # Step 1: Validate match exists (20%)
            tracker.update('validating_match')
            match = _validate_match_exists(match_id)
            
            # Step 2: Check if timeline already exists (40%)
            tracker.update('checking_existing_timeline')
            if _timeline_already_exists(match):
                logger.info(f"Timeline already exists for match {match_id}")
                return {
                    'success': True,
                    'match_id': match_id,
                    'status': 'already_exists'
                }
            
            # Step 3: Fetch timeline data from API (60%)
            tracker.update('fetching_timeline_data')
            timeline_data = _fetch_timeline_data(match_id, platform, routing)
            
            # Step 4: Create timeline record (80%)
            tracker.update('creating_timeline_record')
            timeline = _create_timeline_record(match, timeline_data)
            
            # Step 5: Complete (100%)
            tracker.update('completed')
            
            result = {
                'success': True,
                'match_id': match_id,
                'timeline_id': timeline.id,
                'frame_interval': timeline.frame_interval,
                'status': 'created'
            }
            
            log_task_completion(task, 'sync_match_timeline_atomic', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'sync_match_timeline_atomic')


# Helper functions for timeline processing

def _validate_match_exists(match_id: str) -> Match:
    """Validate that the match exists in the database."""
    match = Match.objects.filter(match_id=match_id).first()
    if not match:
        raise ValueError(f"Match {match_id} not found")
    return match


def _timeline_already_exists(match: Match) -> bool:
    """Check if timeline already exists for the match."""
    return hasattr(match, 'timeline')


def _fetch_timeline_data(match_id: str, platform: str, routing: str) -> Dict:
    """Fetch timeline data from Riot API."""
    client = RiotApiClient(platform=platform, routing=routing)
    return client.get_match_timeline(match_id)


def _create_timeline_record(match: Match, timeline_data: Dict) -> MatchTimeline:
    """Create timeline record from API data."""
    metadata = timeline_data.get('metadata', {})
    info = timeline_data.get('info', {})
    
    timeline = MatchTimeline.objects.create(
        match=match,
        data_version=metadata.get('dataVersion'),
        frame_interval=info.get('frameInterval'),
        raw=timeline_data,
    )
    
    logger.info(f"Created timeline for match {match.match_id}")
    return timeline