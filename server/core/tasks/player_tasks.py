"""
Player data synchronization tasks.

This module contains tasks for:
- Syncing all player data (summoner, matches, timelines)
- Recovering player data with rsync-like functionality
- Managing player data workflows
"""

import logging
from typing import Dict, List, Optional

from django.conf import settings
from django.db import transaction

from ..aggregation import PlayerYearlyStatsAggregator
from ..models import Match, Summoner
from ..riot_service import RiotApiClient
from .match_tasks import sync_match_data_atomic
from .timeline_tasks import sync_match_timeline_atomic
from .utils import (
    TaskProgressTracker,
    handle_task_error,
    log_task_completion,
    log_task_failure,
    log_task_start,
    player_sync_task,
    recovery_task,
    update_task_progress,
    reliable_task
)

logger = logging.getLogger(__name__)


@player_sync_task
def sync_player_data(task, game_name: str, tag_line: str, platform: str = 'na1', routing: str = 'americas', year: Optional[int] = None):
    """
    Sync all data for a player including summoner info, matches, and timelines.
    
    This is the main task that orchestrates the entire data sync process with rsync-like recovery.
    
    Args:
        task: Celery task instance
        game_name: Player's game name
        tag_line: Player's tag line
        platform: Platform (na1, euw1, etc.)
        routing: Routing region (americas, europe, asia)
        year: Year to sync data for (defaults to settings.DEFAULT_MATCH_YEAR)
    
    Returns:
        Dict containing sync results and statistics
    """
    with TaskProgressTracker(task, 'sync_player_data', total_steps=100) as tracker:
        try:
            # Step 1: Fetch and create summoner (5%)
            tracker.update('fetching_summoner')
            summoner = _get_or_create_summoner(game_name, tag_line, platform, routing)
            
            # Step 2: Get match IDs (10%)
            tracker.update('fetching_matches')
            target_year = year or settings.DEFAULT_MATCH_YEAR
            match_ids = _get_match_ids_for_year(summoner, target_year, platform, routing)
            
            # Step 3: Analyze existing data (20%)
            tracker.update('analyzing_existing_data')
            existing_matches, pending_matches = _analyze_existing_data(match_ids)
            
            # Step 4: Process pending matches (70%)
            tracker.update('processing_matches')
            processed_matches, failed_matches = _process_pending_matches(
                pending_matches, platform, routing, summoner.puuid, target_year, task
            )
            
            # Step 5: Update yearly stats (95%)
            tracker.update('updating_stats')
            _update_yearly_stats(summoner, target_year)
            
            # Step 6: Complete (100%)
            tracker.update('completed')
            
            result = {
                'summoner_id': summoner.id,
                'summoner_name': summoner.name,
                'processed_matches': processed_matches,
                'failed_matches': failed_matches,
                'total_matches': len(match_ids),
                'existing_matches': len(existing_matches),
                'year': target_year
            }
            
            log_task_completion(task, 'sync_player_data', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'sync_player_data')


@recovery_task
def recover_player_data(task, game_name: str, tag_line: str, platform: str = 'na1', routing: str = 'americas', year: Optional[int] = None):
    """
    Rsync-like recovery task that can resume from where it left off.
    
    This task checks what data already exists and only processes missing data.
    
    Args:
        task: Celery task instance
        game_name: Player's game name
        tag_line: Player's tag line
        platform: Platform (na1, euw1, etc.)
        routing: Routing region (americas, europe, asia)
        year: Year to recover data for (defaults to settings.DEFAULT_MATCH_YEAR)
    
    Returns:
        Dict containing recovery results and statistics
    """
    with TaskProgressTracker(task, 'recover_player_data', total_steps=100) as tracker:
        try:
            # Step 1: Find existing summoner (5%)
            tracker.update('checking_existing_data')
            summoner = _find_existing_summoner(game_name, tag_line, platform)
            if not summoner:
                raise ValueError(f"Summoner {game_name}#{tag_line} not found")
            
            # Step 2: Get all match IDs (10%)
            tracker.update('fetching_match_ids')
            target_year = year or settings.DEFAULT_MATCH_YEAR
            all_match_ids = _get_match_ids_for_year(summoner, target_year, platform, routing)
            
            # Step 3: Analyze existing data (20%)
            tracker.update('analyzing_data_gaps')
            existing_matches, missing_matches, missing_timelines = _analyze_data_gaps(all_match_ids)
            
            # Step 4: Process missing matches (60%)
            tracker.update('processing_missing_matches')
            processed_matches, failed_matches = _process_missing_matches(
                missing_matches, platform, routing, summoner.puuid, target_year, task
            )
            
            # Step 5: Process missing timelines (80%)
            tracker.update('processing_missing_timelines')
            processed_timelines, failed_timelines = _process_missing_timelines(
                missing_timelines, platform, routing, task
            )
            
            # Step 6: Update yearly stats (95%)
            tracker.update('updating_stats')
            _update_yearly_stats(summoner, target_year)
            
            # Step 7: Complete (100%)
            tracker.update('completed')
            
            result = {
                'success': True,
                'summoner_id': summoner.id,
                'summoner_name': summoner.name,
                'processed_matches': processed_matches,
                'failed_matches': failed_matches,
                'processed_timelines': processed_timelines,
                'failed_timelines': failed_timelines,
                'total_matches': len(all_match_ids),
                'existing_matches': len(existing_matches),
                'year': target_year
            }
            
            log_task_completion(task, 'recover_player_data', result)
            return result
            
        except Exception as e:
            return handle_task_error(task, e, 'recover_player_data')


# Helper functions for player tasks

def _get_or_create_summoner(game_name: str, tag_line: str, platform: str, routing: str) -> Summoner:
    """Get or create summoner record."""
    with transaction.atomic():
        client = RiotApiClient(platform=platform, routing=routing)
        summoner_data = client.get_summoner_by_riot_id(game_name, tag_line)
        
        summoner, created = Summoner.objects.update_or_create(
            puuid=summoner_data.get('puuid'),
            defaults={
                'summoner_id': summoner_data.get('gameName') or summoner_data.get('puuid'),
                'account_id': summoner_data.get('accountId'),
                'name': summoner_data.get('gameName') or game_name,
                'tag_line': summoner_data.get('tagLine') or tag_line,
                'platform': platform,
                'routing': routing,
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} summoner: {summoner.name}")
        return summoner


def _get_match_ids_for_year(summoner: Summoner, year: int, platform: str, routing: str) -> List[str]:
    """Get match IDs for a specific year."""
    client = RiotApiClient(platform=platform, routing=routing)
    match_ids = client.get_match_ids_by_puuid(summoner.puuid, count=100, year=year)
    
    logger.info(f"Found {len(match_ids)} matches for {summoner.name} in {year}")
    return match_ids


def _analyze_existing_data(match_ids: List[str]) -> tuple[List[str], List[str]]:
    """Analyze which matches already exist."""
    existing_matches = set(Match.objects.filter(
        match_id__in=match_ids
    ).values_list('match_id', flat=True))
    
    pending_matches = [mid for mid in match_ids if mid not in existing_matches]
    
    logger.info(f"Found {len(existing_matches)} existing matches, {len(pending_matches)} pending")
    return list(existing_matches), pending_matches


def _analyze_data_gaps(all_match_ids: List[str]) -> tuple[List[str], List[str], List[str]]:
    """Analyze data gaps for recovery."""
    from ..models import MatchTimeline
    
    existing_matches = set(Match.objects.filter(
        match_id__in=all_match_ids
    ).values_list('match_id', flat=True))
    
    existing_timelines = set(MatchTimeline.objects.filter(
        match__match_id__in=all_match_ids
    ).values_list('match__match_id', flat=True))
    
    missing_matches = [mid for mid in all_match_ids if mid not in existing_matches]
    missing_timelines = [mid for mid in existing_matches if mid not in existing_timelines]
    
    logger.info(f"Recovery analysis:")
    logger.info(f"  Total matches: {len(all_match_ids)}")
    logger.info(f"  Existing matches: {len(existing_matches)}")
    logger.info(f"  Missing matches: {len(missing_matches)}")
    logger.info(f"  Missing timelines: {len(missing_timelines)}")
    
    return list(existing_matches), missing_matches, missing_timelines


def _process_pending_matches(
    pending_matches: List[str], 
    platform: str, 
    routing: str, 
    puuid: str, 
    year: int,
    task
) -> tuple[int, List[str]]:
    """Process pending matches with optimized rate limiting for Match API."""
    processed_matches = 0
    failed_matches = []
    
    logger.info(f"Processing {len(pending_matches)} matches with Match API rate limits (2000/10s)...")
    
    # Match API allows 2000 requests every 10 seconds
    # Process in batches of 2000 with 10-second delays
    batch_size = 2000
    delay_between_batches = 10  # 10 seconds between batches
    
    # Split matches into batches
    batches = [pending_matches[i:i + batch_size] for i in range(0, len(pending_matches), batch_size)]
    
    for batch_num, batch in enumerate(batches):
        logger.info(f"Processing batch {batch_num + 1}/{len(batches)} ({len(batch)} matches)")
        
        # Process batch concurrently (up to 2000 requests in 10 seconds)
        batch_results = []
        for match_id in batch:
            try:
                result = sync_match_data_atomic.delay(match_id, platform, routing, puuid, year)
                batch_results.append((match_id, result))
            except Exception as e:
                failed_matches.append(match_id)
                logger.error(f"Error queuing match {match_id}: {str(e)}")
        
        # Wait for batch results
        for match_id, result in batch_results:
            try:
                match_result = result.get(timeout=30)
                
                if match_result.get('success'):
                    processed_matches += 1
                    logger.info(f"Successfully processed match {match_id}")
                else:
                    failed_matches.append(match_id)
                    logger.error(f"Failed to process match {match_id}: {match_result.get('error')}")
                    
            except Exception as e:
                failed_matches.append(match_id)
                logger.error(f"Error processing match {match_id}: {str(e)}")
        
        # Update progress
        progress = 20 + ((batch_num + 1) / len(batches)) * 70
        update_task_progress(task, 'processing_matches', int(progress), 
                           processed=processed_matches, failed=len(failed_matches),
                           current_batch=f"{batch_num + 1}/{len(batches)}")
        
        # Wait between batches to respect rate limits
        if batch_num < len(batches) - 1:  # Don't wait after the last batch
            logger.info(f"Waiting {delay_between_batches}s before next batch...")
            import time
            time.sleep(delay_between_batches)
    
    logger.info(f"Completed processing: {processed_matches} successful, {len(failed_matches)} failed")
    return processed_matches, failed_matches


def _process_missing_matches(
    missing_matches: List[str], 
    platform: str, 
    routing: str, 
    puuid: str, 
    year: int,
    task
) -> tuple[int, List[str]]:
    """Process missing matches for recovery."""
    processed_matches = 0
    failed_matches = []
    
    for i, match_id in enumerate(missing_matches):
        try:
            result = sync_match_data_atomic.delay(match_id, platform, routing, puuid, year)
            match_result = result.get(timeout=30)
            
            if match_result.get('success'):
                processed_matches += 1
            else:
                failed_matches.append(match_id)
            
            progress = 20 + ((i + 1) / len(missing_matches)) * 60
            update_task_progress(task, 'processing_missing_matches', int(progress),
                               processed=processed_matches, failed=len(failed_matches),
                               current_match=match_id)
            
        except Exception as e:
            failed_matches.append(match_id)
            logger.error(f"Error processing match {match_id}: {str(e)}")
    
    return processed_matches, failed_matches


def _process_missing_timelines(
    missing_timelines: List[str], 
    platform: str, 
    routing: str,
    task
) -> tuple[int, List[str]]:
    """Process missing timelines for recovery."""
    processed_timelines = 0
    failed_timelines = []
    
    for i, match_id in enumerate(missing_timelines):
        try:
            result = sync_match_timeline_atomic.delay(match_id, platform, routing)
            timeline_result = result.get(timeout=30)
            
            if timeline_result.get('success'):
                processed_timelines += 1
            else:
                failed_timelines.append(match_id)
            
            progress = 80 + ((i + 1) / len(missing_timelines)) * 15
            update_task_progress(task, 'processing_missing_timelines', int(progress),
                               processed_timelines=processed_timelines, 
                               failed_timelines=len(failed_timelines))
            
        except Exception as e:
            failed_timelines.append(match_id)
            logger.error(f"Error processing timeline {match_id}: {str(e)}")
    
    return processed_timelines, failed_timelines


def _update_yearly_stats(summoner: Summoner, year: int):
    """Update yearly statistics for summoner."""
    try:
        aggregator = PlayerYearlyStatsAggregator(summoner, year)
        aggregator.update_stats()
        logger.info(f"Updated yearly stats for {summoner.name}")
    except Exception as e:
        logger.error(f"Error updating yearly stats: {str(e)}")


def _find_existing_summoner(game_name: str, tag_line: str, platform: str) -> Optional[Summoner]:
    """Find existing summoner record."""
    return Summoner.objects.filter(
        name=game_name,
        tag_line=tag_line,
        platform=platform
    ).first()


@reliable_task(queue='recovery', rate_limit='1/m')
def auto_retry_failed_matches():
    """
    Automatically retry failed matches for all summoners.
    This task can be scheduled to run periodically.
    """
    logger.info("Starting auto-retry of failed matches...")
    
    # Find summoners with recent failed matches
    from ..models import Match, MatchParticipant
    
    # Get summoners who have matches but might have failed ones
    summoners_with_matches = Summoner.objects.filter(
        participants__isnull=False
    ).distinct()
    
    retry_count = 0
    for summoner in summoners_with_matches:
        try:
            # Use recovery task to retry failed matches
            result = recover_player_data.delay(
                game_name=summoner.name,
                tag_line=summoner.tag_line,
                platform=summoner.platform,
                routing=summoner.routing,
                year=2025
            )
            retry_count += 1
            logger.info(f"Queued recovery for {summoner.name}#{summoner.tag_line}")
            
        except Exception as e:
            logger.error(f"Error queuing recovery for {summoner.name}: {e}")
    
    logger.info(f"Queued {retry_count} recovery tasks")
    return {'retry_count': retry_count}