"""
Aggregation utilities for PlayerYearlyStats.
This module handles the calculation and updating of yearly statistics.
"""
import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from .models import Match, MatchParticipant, PlayerYearlyStats, Summoner

logger = logging.getLogger(__name__)


class PlayerYearlyStatsAggregator:
    """
    Handles aggregation of player statistics for a given year.
    """
    
    def __init__(self, summoner: Summoner, year: int):
        self.summoner = summoner
        self.year = year
        self.platform = summoner.platform
    
    def get_or_create_stats(self) -> PlayerYearlyStats:
        """Get or create PlayerYearlyStats record for the summoner and year."""
        stats, created = PlayerYearlyStats.objects.get_or_create(
            summoner=self.summoner,
            year=self.year,
            platform=self.platform,
            defaults={
                'total_matches': 0,
                'wins': 0,
                'losses': 0,
                'total_kills': 0,
                'total_deaths': 0,
                'total_assists': 0,
                'total_gold_earned': 0,
                'total_minions_killed': 0,
                'total_neutral_minions_killed': 0,
                'total_damage_to_champions': 0,
                'unique_champions_played': 0,
                'unique_roles_played': 0,
                'unique_lanes_played': 0,
            }
        )
        
        if created:
            logger.info(f"Created new yearly stats for {self.summoner.name} ({self.year})")
        else:
            logger.info(f"Found existing yearly stats for {self.summoner.name} ({self.year})")
        
        return stats
    
    def calculate_stats_from_matches(self, match_ids: Optional[List[str]] = None) -> Dict:
        """
        Calculate aggregated statistics from match participants.
        If match_ids is provided, only calculate from those specific matches.
        """
        # Get all match participants for this summoner in the given year
        participants_query = MatchParticipant.objects.filter(
            summoner=self.summoner,
            match__platform=self.platform
        )
        
        # Filter by year if needed
        if self.year:
            start_date = timezone.datetime(self.year, 1, 1)
            end_date = timezone.datetime(self.year + 1, 1, 1)
            participants_query = participants_query.filter(
                match__game_creation__gte=start_date,
                match__game_creation__lt=end_date
            )
        
        # Filter by specific match IDs if provided
        if match_ids:
            participants_query = participants_query.filter(match__match_id__in=match_ids)
        
        participants = list(participants_query.select_related('match'))
        
        if not participants:
            logger.warning(f"No participants found for {self.summoner.name} in {self.year}")
            return self._get_empty_stats()
        
        # Calculate aggregated statistics
        stats = self._get_empty_stats()
        
        # Basic counts
        stats['total_matches'] = len(participants)
        stats['wins'] = sum(1 for p in participants if p.win)
        stats['losses'] = stats['total_matches'] - stats['wins']
        
        # Aggregated stats
        stats['total_kills'] = sum(p.kills for p in participants)
        stats['total_deaths'] = sum(p.deaths for p in participants)
        stats['total_assists'] = sum(p.assists for p in participants)
        stats['total_gold_earned'] = sum(p.gold_earned for p in participants)
        stats['total_minions_killed'] = sum(p.total_minions_killed for p in participants)
        stats['total_neutral_minions_killed'] = sum(p.neutral_minions_killed for p in participants)
        stats['total_damage_to_champions'] = sum(p.damage_to_champions for p in participants)
        
        # Diversity stats
        champions = [p.champion_name for p in participants if p.champion_name]
        roles = [p.role for p in participants if p.role]
        lanes = [p.lane for p in participants if p.lane]
        
        stats['unique_champions_played'] = len(set(champions))
        stats['unique_roles_played'] = len(set(roles))
        stats['unique_lanes_played'] = len(set(lanes))
        
        # Most played champion
        if champions:
            champion_counts = Counter(champions)
            most_played = champion_counts.most_common(1)[0]
            stats['most_played_champion'] = most_played[0]
            stats['most_played_champion_count'] = most_played[1]
        
        # Calculate derived stats
        self._calculate_derived_stats(stats)
        
        logger.info(f"Calculated stats for {self.summoner.name} ({self.year}): "
                   f"{stats['total_matches']} matches, {stats['wins']} wins")
        
        return stats
    
    def _get_empty_stats(self) -> Dict:
        """Return empty stats dictionary."""
        return {
            'total_matches': 0,
            'wins': 0,
            'losses': 0,
            'total_kills': 0,
            'total_deaths': 0,
            'total_assists': 0,
            'total_gold_earned': 0,
            'total_minions_killed': 0,
            'total_neutral_minions_killed': 0,
            'total_damage_to_champions': 0,
            'unique_champions_played': 0,
            'most_played_champion': None,
            'most_played_champion_count': 0,
            'unique_roles_played': 0,
            'unique_lanes_played': 0,
            'win_rate': 0.0,
            'kda_ratio': 0.0,
            'average_kills': 0.0,
            'average_deaths': 0.0,
            'average_assists': 0.0,
            'average_gold_per_match': 0.0,
            'average_cs_per_match': 0.0,
        }
    
    def _calculate_derived_stats(self, stats: Dict):
        """Calculate derived statistics from base stats."""
        if stats['total_matches'] > 0:
            stats['win_rate'] = (stats['wins'] / stats['total_matches']) * 100
            stats['average_kills'] = stats['total_kills'] / stats['total_matches']
            stats['average_deaths'] = stats['total_deaths'] / stats['total_matches']
            stats['average_assists'] = stats['total_assists'] / stats['total_matches']
            stats['average_gold_per_match'] = stats['total_gold_earned'] / stats['total_matches']
            stats['average_cs_per_match'] = (
                stats['total_minions_killed'] + stats['total_neutral_minions_killed']
            ) / stats['total_matches']
            
            # KDA calculation
            if stats['total_deaths'] > 0:
                stats['kda_ratio'] = (stats['total_kills'] + stats['total_assists']) / stats['total_deaths']
            else:
                stats['kda_ratio'] = stats['total_kills'] + stats['total_assists']
    
    @transaction.atomic
    def update_stats(self, match_ids: Optional[List[str]] = None) -> PlayerYearlyStats:
        """
        Update PlayerYearlyStats with current data.
        This method is atomic to ensure data consistency.
        """
        stats = self.get_or_create_stats()
        calculated_stats = self.calculate_stats_from_matches(match_ids)
        
        # Update all fields
        for field, value in calculated_stats.items():
            setattr(stats, field, value)
        
        # Save the updated stats
        stats.save()
        
        logger.info(f"Updated yearly stats for {self.summoner.name} ({self.year})")
        return stats
    
    @transaction.atomic
    def increment_stats(self, participant: MatchParticipant) -> PlayerYearlyStats:
        """
        Incrementally update stats by adding a single match participant.
        This is more efficient than recalculating everything.
        """
        stats = self.get_or_create_stats()
        
        # Increment basic counts
        stats.total_matches += 1
        if participant.win:
            stats.wins += 1
        else:
            stats.losses += 1
        
        # Increment aggregated stats
        stats.total_kills += participant.kills
        stats.total_deaths += participant.deaths
        stats.total_assists += participant.assists
        stats.total_gold_earned += participant.gold_earned
        stats.total_minions_killed += participant.total_minions_killed
        stats.total_neutral_minions_killed += participant.neutral_minions_killed
        stats.total_damage_to_champions += participant.damage_to_champions
        
        # Update diversity stats (this is approximate for incremental updates)
        # For exact diversity stats, we'd need to recalculate from all matches
        if participant.champion_name:
            # Simple heuristic: if this is a new champion, increment unique count
            existing_champions = MatchParticipant.objects.filter(
                summoner=self.summoner,
                match__platform=self.platform,
                champion_name__isnull=False
            ).exclude(id=participant.id).values_list('champion_name', flat=True).distinct()
            
            if participant.champion_name not in existing_champions:
                stats.unique_champions_played += 1
        
        # Recalculate derived stats
        stats.calculate_derived_stats()
        stats.save()
        
        logger.info(f"Incremented yearly stats for {self.summoner.name} ({self.year})")
        return stats


def recalculate_all_yearly_stats(year: int, platform: str = None) -> Dict[str, int]:
    """
    Recalculate yearly stats for all players in a given year.
    This is useful for data consistency checks or bulk updates.
    """
    logger.info(f"Starting recalculation of yearly stats for {year}")
    
    # Get all summoners
    summoners_query = Summoner.objects.all()
    if platform:
        summoners_query = summoners_query.filter(platform=platform)
    
    summoners = summoners_query.all()
    updated_count = 0
    error_count = 0
    
    for summoner in summoners:
        try:
            aggregator = PlayerYearlyStatsAggregator(summoner, year)
            aggregator.update_stats()
            updated_count += 1
        except Exception as e:
            logger.error(f"Error updating stats for {summoner.name}: {str(e)}")
            error_count += 1
    
    result = {
        'updated': updated_count,
        'errors': error_count,
        'total': len(summoners)
    }
    
    logger.info(f"Completed recalculation: {result}")
    return result