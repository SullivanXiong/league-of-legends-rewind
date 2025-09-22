import logging
from datetime import datetime
from typing import Dict, List, Optional

from celery import shared_task
from django.conf import settings
from django.utils.dateparse import parse_datetime

from .models import Match, MatchParticipant, MatchTimeline, Summoner
from .riot_service import RiotApiClient

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def sync_player_data(self, game_name: str, tag_line: str, platform: str = 'na1', routing: str = 'americas', year: Optional[int] = None):
    """
    Sync all data for a player including summoner info, matches, and timelines.
    This is the main task that orchestrates the entire data sync process.
    """
    try:
        # Update task state
        self.update_state(state='PROGRESS', meta={'step': 'fetching_summoner', 'progress': 10})
        
        # Get or create summoner
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
        
        # Update progress
        self.update_state(state='PROGRESS', meta={'step': 'fetching_matches', 'progress': 30})
        
        # Get match IDs for the specified year (default to 2025)
        target_year = year or settings.DEFAULT_MATCH_YEAR
        match_ids = client.get_match_ids_by_puuid(summoner.puuid, count=100, year=target_year)
        
        logger.info(f"Found {len(match_ids)} matches for {summoner.name} in {target_year}")
        
        # Update progress
        self.update_state(state='PROGRESS', meta={'step': 'processing_matches', 'progress': 50})
        
        # Process matches in batches
        processed_matches = 0
        total_matches = len(match_ids)
        
        for i, match_id in enumerate(match_ids):
            try:
                # Check if match already exists
                if Match.objects.filter(match_id=match_id).exists():
                    logger.info(f"Match {match_id} already exists, skipping")
                    continue
                
                # Sync individual match
                sync_match_data.delay(match_id, platform, routing, summoner.puuid)
                processed_matches += 1
                
                # Update progress
                progress = 50 + (i / total_matches) * 40
                self.update_state(state='PROGRESS', meta={
                    'step': 'processing_matches',
                    'progress': int(progress),
                    'processed': processed_matches,
                    'total': total_matches
                })
                
            except Exception as e:
                logger.error(f"Error processing match {match_id}: {str(e)}")
                continue
        
        # Update final state
        self.update_state(state='SUCCESS', meta={
            'step': 'completed',
            'progress': 100,
            'processed_matches': processed_matches,
            'total_matches': total_matches,
            'summoner_id': summoner.id,
            'summoner_name': summoner.name
        })
        
        return {
            'summoner_id': summoner.id,
            'summoner_name': summoner.name,
            'processed_matches': processed_matches,
            'total_matches': total_matches,
            'year': target_year
        }
        
    except Exception as e:
        logger.error(f"Error in sync_player_data: {str(e)}")
        self.update_state(state='FAILURE', meta={'error': str(e)})
        raise


@shared_task(bind=True)
def sync_match_data(self, match_id: str, platform: str, routing: str, puuid: str):
    """
    Sync individual match data including participants and timeline.
    """
    try:
        client = RiotApiClient(platform=platform, routing=routing)
        
        # Get match data
        raw_match_data = client.get_match(match_id)
        info = raw_match_data.get('info', {})
        meta = raw_match_data.get('metadata', {})
        
        # Create or update match
        match, created = Match.objects.update_or_create(
            match_id=match_id,
            defaults={
                'data_version': meta.get('dataVersion'),
                'game_creation': parse_datetime(str(info.get('gameCreation'))) if info.get('gameCreation') else None,
                'game_duration': info.get('gameDuration'),
                'queue_id': info.get('queueId'),
                'platform': platform,
                'routing': routing,
                'raw': raw_match_data,
            }
        )
        
        logger.info(f"{'Created' if created else 'Updated'} match: {match_id}")
        
        # Process participants
        participants = info.get('participants', [])
        for participant_data in participants:
            participant_puuid = participant_data.get('puuid')
            if not participant_puuid:
                continue
                
            # Get or create summoner for participant
            summoner, _ = Summoner.objects.get_or_create(
                puuid=participant_puuid,
                defaults={
                    'summoner_id': participant_data.get('summonerId') or participant_puuid,
                    'name': participant_data.get('summonerName') or 'Unknown',
                    'platform': platform,
                    'routing': routing,
                }
            )
            
            # Create or update match participant
            MatchParticipant.objects.update_or_create(
                match=match,
                puuid=participant_puuid,
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
                    'perk_primary_style': (participant_data.get('perks', {}).get('styles') or [{}])[0].get('style'),
                    'perk_sub_style': (participant_data.get('perks', {}).get('styles') or [{}, {}])[1].get('style') if len((participant_data.get('perks', {}).get('styles') or [])) > 1 else None,
                }
            )
        
        # Sync timeline data if this is the requested player's match
        if puuid in [p.get('puuid') for p in participants]:
            sync_match_timeline.delay(match_id, platform, routing)
        
        return {
            'match_id': match_id,
            'created': created,
            'participants_count': len(participants)
        }
        
    except Exception as e:
        logger.error(f"Error syncing match {match_id}: {str(e)}")
        raise


@shared_task(bind=True)
def sync_match_timeline(self, match_id: str, platform: str, routing: str):
    """
    Sync timeline data for a specific match.
    """
    try:
        # Check if timeline already exists
        match = Match.objects.filter(match_id=match_id).first()
        if not match:
            logger.error(f"Match {match_id} not found")
            return {'error': 'Match not found'}
        
        if hasattr(match, 'timeline'):
            logger.info(f"Timeline already exists for match {match_id}")
            return {'match_id': match_id, 'status': 'already_exists'}
        
        client = RiotApiClient(platform=platform, routing=routing)
        timeline_data = client.get_match_timeline(match_id)
        
        # Extract metadata from timeline data
        metadata = timeline_data.get('metadata', {})
        info = timeline_data.get('info', {})
        
        # Create timeline
        timeline = MatchTimeline.objects.create(
            match=match,
            data_version=metadata.get('dataVersion'),
            frame_interval=info.get('frameInterval'),
            raw=timeline_data,
        )
        
        logger.info(f"Created timeline for match {match_id}")
        
        return {
            'match_id': match_id,
            'timeline_id': timeline.id,
            'frame_interval': timeline.frame_interval
        }
        
    except Exception as e:
        logger.error(f"Error syncing timeline for match {match_id}: {str(e)}")
        raise


@shared_task
def cleanup_old_data(days: int = 30):
    """
    Cleanup old data to prevent database bloat.
    """
    from django.utils import timezone
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days)
    
    # Delete old matches and related data
    old_matches = Match.objects.filter(created_at__lt=cutoff_date)
    count = old_matches.count()
    old_matches.delete()
    
    logger.info(f"Cleaned up {count} old matches")
    return {'cleaned_matches': count}