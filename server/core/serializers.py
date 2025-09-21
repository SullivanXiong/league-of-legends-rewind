from rest_framework import serializers

from .models import Match, MatchParticipant, Summoner


class SummonerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Summoner
        fields = [
            'id', 'puuid', 'summoner_id', 'account_id', 'name', 'tag_line',
            'profile_icon_id', 'summoner_level', 'platform', 'routing',
            'last_updated', 'created_at'
        ]


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


class MatchSerializer(serializers.ModelSerializer):
    participants = MatchParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Match
        fields = [
            'id', 'match_id', 'data_version', 'game_creation', 'game_duration',
            'queue_id', 'platform', 'routing', 'raw', 'created_at', 'participants'
        ]

