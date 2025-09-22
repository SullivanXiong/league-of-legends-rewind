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
