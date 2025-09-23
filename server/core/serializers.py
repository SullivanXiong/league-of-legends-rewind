from rest_framework import serializers

from .models import Match, MatchParticipant, MatchTimeline, PlayerYearlyStats, Summoner


class MatchParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchParticipant
        fields = [
            'id', 'match', 'summoner', 'puuid', 'summoner_name', 'team_id',
            'champion_id', 'champion_name', 'role', 'lane', 'kills', 'deaths',
            'assists', 'win', 'gold_earned', 'total_minions_killed',
            'neutral_minions_killed', 'damage_to_champions', 'item0', 'item1',
            'item2', 'item3', 'item4', 'item5', 'item6', 'spell1', 'spell2',
            'perk_primary_style', 'perk_sub_style'
        ]


class MatchTimelineSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchTimeline
        fields = [
            'id', 'match', 'data_version', 'frame_interval', 'raw', 'created_at'
        ]


class PlayerYearlyStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerYearlyStats
        fields = [
            'id', 'summoner', 'year', 'platform', 'total_matches', 'wins', 'losses',
            'total_kills', 'total_deaths', 'total_assists', 'total_gold_earned',
            'total_minions_killed', 'total_neutral_minions_killed', 'total_damage_to_champions',
            'unique_champions_played', 'most_played_champion', 'most_played_champion_count',
            'unique_roles_played', 'unique_lanes_played', 'win_rate', 'kda_ratio',
            'average_kills', 'average_deaths', 'average_assists', 'average_gold_per_match',
            'average_cs_per_match', 'last_updated', 'created_at'
        ]


class SummonerSerializer(serializers.ModelSerializer):
    yearly_stats = PlayerYearlyStatsSerializer(many=True, read_only=True)
    
    class Meta:
        model = Summoner
        fields = [
            'id', 'puuid', 'summoner_id', 'account_id', 'name', 'tag_line',
            'profile_icon_id', 'summoner_level', 'platform', 'routing',
            'last_updated', 'created_at', 'yearly_stats'
        ]


class MatchSerializer(serializers.ModelSerializer):
    participants = MatchParticipantSerializer(many=True, read_only=True)
    timeline = MatchTimelineSerializer(read_only=True)

    class Meta:
        model = Match
        fields = [
            'id', 'match_id', 'data_version', 'game_creation', 'game_duration',
            'queue_id', 'platform', 'routing', 'raw', 'created_at', 'participants', 'timeline'
        ]

