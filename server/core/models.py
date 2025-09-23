from django.db import models


class Summoner(models.Model):
    puuid = models.CharField(max_length=78, unique=True)
    summoner_id = models.CharField(max_length=63, unique=True)
    account_id = models.CharField(max_length=56, blank=True, null=True)
    name = models.CharField(max_length=30, db_index=True)
    tag_line = models.CharField(max_length=5, blank=True, null=True)
    profile_icon_id = models.IntegerField(blank=True, null=True)
    summoner_level = models.IntegerField(default=0)
    platform = models.CharField(max_length=10, help_text='e.g. na1, euw1')
    routing = models.CharField(max_length=10, help_text='e.g. americas, europe, asia')
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['platform']),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.platform})"


class Match(models.Model):
    match_id = models.CharField(max_length=30, unique=True)
    data_version = models.CharField(max_length=10, blank=True, null=True)
    game_creation = models.DateTimeField(blank=True, null=True)
    game_duration = models.IntegerField(blank=True, null=True)
    queue_id = models.IntegerField(blank=True, null=True)
    platform = models.CharField(max_length=10)
    routing = models.CharField(max_length=10)
    raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['platform']),
            models.Index(fields=['routing']),
        ]

    def __str__(self) -> str:
        return self.match_id


class MatchParticipant(models.Model):
    match = models.ForeignKey(Match, related_name='participants', on_delete=models.CASCADE)
    summoner = models.ForeignKey(Summoner, related_name='participants', on_delete=models.CASCADE)
    puuid = models.CharField(max_length=78)
    summoner_name = models.CharField(max_length=30)
    team_id = models.IntegerField()
    champion_id = models.IntegerField(blank=True, null=True)
    champion_name = models.CharField(max_length=40, blank=True, null=True)
    role = models.CharField(max_length=20, blank=True, null=True)
    lane = models.CharField(max_length=20, blank=True, null=True)
    kills = models.IntegerField(default=0)
    deaths = models.IntegerField(default=0)
    assists = models.IntegerField(default=0)
    win = models.BooleanField(default=False)
    gold_earned = models.IntegerField(default=0)
    total_minions_killed = models.IntegerField(default=0)
    neutral_minions_killed = models.IntegerField(default=0)
    damage_to_champions = models.IntegerField(default=0)
    item0 = models.IntegerField(blank=True, null=True)
    item1 = models.IntegerField(blank=True, null=True)
    item2 = models.IntegerField(blank=True, null=True)
    item3 = models.IntegerField(blank=True, null=True)
    item4 = models.IntegerField(blank=True, null=True)
    item5 = models.IntegerField(blank=True, null=True)
    item6 = models.IntegerField(blank=True, null=True)
    spell1 = models.IntegerField(blank=True, null=True)
    spell2 = models.IntegerField(blank=True, null=True)
    perk_primary_style = models.IntegerField(blank=True, null=True)
    perk_sub_style = models.IntegerField(blank=True, null=True)

    class Meta:
        unique_together = ('match', 'puuid')
        indexes = [
            models.Index(fields=['puuid']),
            models.Index(fields=['summoner']),
        ]

    def __str__(self) -> str:
        return f"{self.summoner_name} - {self.match.match_id}"


class MatchTimeline(models.Model):
    match = models.OneToOneField(Match, related_name='timeline', on_delete=models.CASCADE)
    data_version = models.CharField(max_length=10, blank=True, null=True)
    frame_interval = models.IntegerField(blank=True, null=True, help_text='Interval between frames in milliseconds')
    raw = models.JSONField(default=dict, blank=True, help_text='Raw timeline data from Riot API')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['match']),
        ]

    def __str__(self) -> str:
        return f"Timeline for {self.match.match_id}"


class PlayerYearlyStats(models.Model):
    """
    Aggregated yearly statistics for a player across all their matches.
    This table provides fast access to aggregated data without needing to
    calculate sums/averages across multiple tables.
    """
    summoner = models.ForeignKey(Summoner, related_name='yearly_stats', on_delete=models.CASCADE)
    year = models.IntegerField()
    platform = models.CharField(max_length=10)
    
    # Match counts
    total_matches = models.IntegerField(default=0)
    wins = models.IntegerField(default=0)
    losses = models.IntegerField(default=0)
    
    # Aggregated stats
    total_kills = models.IntegerField(default=0)
    total_deaths = models.IntegerField(default=0)
    total_assists = models.IntegerField(default=0)
    total_gold_earned = models.BigIntegerField(default=0)
    total_minions_killed = models.IntegerField(default=0)
    total_neutral_minions_killed = models.IntegerField(default=0)
    total_damage_to_champions = models.BigIntegerField(default=0)
    
    # Champion diversity
    unique_champions_played = models.IntegerField(default=0)
    most_played_champion = models.CharField(max_length=40, blank=True, null=True)
    most_played_champion_count = models.IntegerField(default=0)
    
    # Role/Lane diversity
    unique_roles_played = models.IntegerField(default=0)
    unique_lanes_played = models.IntegerField(default=0)
    
    # Calculated fields (can be computed from above)
    win_rate = models.FloatField(default=0.0)
    kda_ratio = models.FloatField(default=0.0)
    average_kills = models.FloatField(default=0.0)
    average_deaths = models.FloatField(default=0.0)
    average_assists = models.FloatField(default=0.0)
    average_gold_per_match = models.FloatField(default=0.0)
    average_cs_per_match = models.FloatField(default=0.0)
    
    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('summoner', 'year', 'platform')
        indexes = [
            models.Index(fields=['summoner', 'year']),
            models.Index(fields=['year', 'platform']),
            models.Index(fields=['win_rate']),
            models.Index(fields=['total_matches']),
        ]
    
    def __str__(self) -> str:
        return f"{self.summoner.name} - {self.year} ({self.platform})"
    
    def calculate_derived_stats(self):
        """Calculate derived statistics from base stats."""
        if self.total_matches > 0:
            self.win_rate = (self.wins / self.total_matches) * 100
            self.average_kills = self.total_kills / self.total_matches
            self.average_deaths = self.total_deaths / self.total_matches
            self.average_assists = self.total_assists / self.total_matches
            self.average_gold_per_match = self.total_gold_earned / self.total_matches
            self.average_cs_per_match = (self.total_minions_killed + self.total_neutral_minions_killed) / self.total_matches
            
            # KDA calculation: (Kills + Assists) / Deaths (avoid division by zero)
            if self.total_deaths > 0:
                self.kda_ratio = (self.total_kills + self.total_assists) / self.total_deaths
            else:
                self.kda_ratio = self.total_kills + self.total_assists  # Perfect KDA
        else:
            self.win_rate = 0.0
            self.average_kills = 0.0
            self.average_deaths = 0.0
            self.average_assists = 0.0
            self.average_gold_per_match = 0.0
            self.average_cs_per_match = 0.0
            self.kda_ratio = 0.0
