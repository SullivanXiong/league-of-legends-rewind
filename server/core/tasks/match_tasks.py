"""
Individual match processing tasks.

This module contains tasks for:
- Processing individual match data atomically
- Creating match participants
- Updating yearly statistics incrementally
"""

import logging
from typing import Dict, List

from django.db import transaction
from django.utils.dateparse import parse_datetime

from ..aggregation import PlayerYearlyStatsAggregator
from ..models import Match, MatchParticipant, Summoner
from ..riot_service import RiotApiClient
from .timeline_tasks import sync_match_timeline_atomic
from .utils import (
    TaskProgressTracker,
    handle_task_error,
    log_task_completion,
    match_processing_task,
    update_task_progress
)

logger = logging.getLogger(__name__)


@match_processing_task
def sync_match_data_atomic(task, match_id: str, platform: str, routing: str, puuid: str, year: int):
    """
    Sync individual match data atomically including participants and timeline.
    
    This ensures all-or-nothing data consistency for each match.
    
    Args:
        task: Celery task instance
        match_id: Riot match ID
        platform: Platform (na1, euw1, etc.)
        routing: Routing region (americas, europe, asia)
        puuid: Player's PUUID (for timeline sync)
        year: Year for statistics aggregation
    
    Returns:
        Dict containing match processing results
    """
    with TaskProgressTracker(task, 'sync_match_data_atomic', total_steps=100) as tracker:
        try:
            # Step 1: Fetch match data from API (20%)
            tracker.update('fetching_match_data')
            match_data = _fetch_match_data(match_id, platform, routing)
            
            # Step 2: Create/update match record (30%)
            tracker.update('creating_match_record')
            match = _create_match_record(match_id, match_data, platform, routing)
            
            # Step 3: Process participants (60%)
            tracker.update('processing_participants')
            participants = _process_participants(match, match_data, platform, routing, year)
            
            # Step 4: Sync timeline if needed (80%)
            tracker.update('syncing_timeline')
            timeline_synced = _sync_timeline_if_needed(match_id, platform, routing, puuid, match_data)
            
            # Step 5: Complete (100%)
            tracker.update('completed')
            
            result = {
                'success': True,
                'match_id': match_id,
                'created': not hasattr(match, 'id') or match.id is None,
                'participants_count': len(participants),
                'timeline_synced': timeline_synced
            }
            
            log_task_completion(task, 'sync_match_data_atomic', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'sync_match_data_atomic')


# Helper functions for match processing

def _fetch_match_data(match_id: str, platform: str, routing: str) -> Dict:
    """Fetch match data from Riot API."""
    client = RiotApiClient(platform=platform, routing=routing)
    return client.get_match(match_id)


def _create_match_record(match_id: str, match_data: Dict, platform: str, routing: str) -> Match:
    """Create or update match record."""
    info = match_data.get('info', {})
    meta = match_data.get('metadata', {})
    
    match, created = Match.objects.update_or_create(
        match_id=match_id,
        defaults={
            'data_version': meta.get('dataVersion'),
            'game_creation': parse_datetime(str(info.get('gameCreation'))) if info.get('gameCreation') else None,
            'game_duration': info.get('gameDuration'),
            'queue_id': info.get('queueId'),
            'platform': platform,
            'routing': routing,
            'raw': match_data,
        }
    )
    
    logger.info(f"{'Created' if created else 'Updated'} match: {match_id}")
    return match


def _process_participants(match: Match, match_data: Dict, platform: str, routing: str, year: int) -> List[MatchParticipant]:
    """Process all match participants."""
    participants_data = match_data.get('info', {}).get('participants', [])
    processed_participants = []
    
    for participant_data in participants_data:
        participant_puuid = participant_data.get('puuid')
        if not participant_puuid:
            continue
            
        # Get or create summoner for participant
        summoner = _get_or_create_participant_summoner(participant_data, platform, routing)
        
        # Create or update match participant
        participant = _create_match_participant(match, summoner, participant_data)
        processed_participants.append(participant)
        
        # Update yearly stats incrementally
        _update_yearly_stats_incremental(summoner, participant, year)
    
    logger.info(f"Processed {len(processed_participants)} participants for match {match.match_id}")
    return processed_participants


def _get_or_create_participant_summoner(participant_data: Dict, platform: str, routing: str) -> Summoner:
    """Get or create summoner record for participant."""
    participant_puuid = participant_data.get('puuid')
    
    summoner, _ = Summoner.objects.get_or_create(
        puuid=participant_puuid,
        defaults={
            'summoner_id': participant_data.get('summonerId') or participant_puuid,
            'name': participant_data.get('summonerName') or 'Unknown',
            'platform': platform,
            'routing': routing,
        }
    )
    
    return summoner


def _create_match_participant(match: Match, summoner: Summoner, participant_data: Dict) -> MatchParticipant:
    """Create or update match participant record."""
    participant, created = MatchParticipant.objects.update_or_create(
        match=match,
        puuid=participant_data.get('puuid'),
        defaults={
            'summoner': summoner,
            'summoner_name': participant_data.get('summonerName') or '',
            'team_id': participant_data.get('teamId') or 0,
            'champion_id': participant_data.get('championId'),
            'champion_name': participant_data.get('championName'),
            'role': participant_data.get('role'),
            'lane': participant_data.get('lane'),
            'kills': participant_data.get('kills', 0),
            'deaths': participant_data.get('deaths', 0),
            'assists': participant_data.get('assists', 0),
            'win': bool(participant_data.get('win', False)),
            'gold_earned': participant_data.get('goldEarned', 0),
            'total_minions_killed': participant_data.get('totalMinionsKilled', 0),
            'neutral_minions_killed': participant_data.get('neutralMinionsKilled', 0),
            'damage_to_champions': participant_data.get('totalDamageDealtToChampions', 0),
            'item0': participant_data.get('item0'),
            'item1': participant_data.get('item1'),
            'item2': participant_data.get('item2'),
            'item3': participant_data.get('item3'),
            'item4': participant_data.get('item4'),
            'item5': participant_data.get('item5'),
            'item6': participant_data.get('item6'),
            'spell1': participant_data.get('summoner1Id'),
            'spell2': participant_data.get('summoner2Id'),
            'perk_primary_style': _extract_perk_style(participant_data, 0),
            'perk_sub_style': _extract_perk_style(participant_data, 1),
        }
    )
    
    return participant


def _extract_perk_style(participant_data: Dict, index: int) -> int:
    """Extract perk style from participant data."""
    perks = participant_data.get('perks', {})
    styles = perks.get('styles', [])
    
    if index < len(styles):
        return styles[index].get('style')
    
    return None


def _update_yearly_stats_incremental(summoner: Summoner, participant: MatchParticipant, year: int):
    """Update yearly stats incrementally for a participant."""
    try:
        aggregator = PlayerYearlyStatsAggregator(summoner, year)
        aggregator.increment_stats(participant)
    except Exception as e:
        logger.error(f"Error updating yearly stats for {summoner.name}: {str(e)}")


def _sync_timeline_if_needed(match_id: str, platform: str, routing: str, puuid: str, match_data: Dict) -> bool:
    """Sync timeline data if this is the requested player's match."""
    participants = match_data.get('info', {}).get('participants', [])
    participant_puuids = [p.get('puuid') for p in participants]
    
    if puuid in participant_puuids:
        try:
            sync_match_timeline_atomic.delay(match_id, platform, routing)
            return True
        except Exception as e:
            logger.error(f"Error syncing timeline for {match_id}: {str(e)}")
            return False
    
    return False