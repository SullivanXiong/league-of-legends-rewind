from django.contrib import admin

from .models import Match, MatchParticipant, MatchTimeline, PlayerYearlyStats, Summoner


@admin.register(Summoner)
class SummonerAdmin(admin.ModelAdmin):
    list_display = ('name', 'tag_line', 'platform', 'routing', 'summoner_level', 'last_updated')
    search_fields = ('name', 'puuid', 'summoner_id')
    list_filter = ('platform', 'routing')


class MatchParticipantInline(admin.TabularInline):
    model = MatchParticipant
    extra = 0


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('match_id', 'platform', 'routing', 'queue_id', 'game_duration', 'created_at')
    search_fields = ('match_id',)
    list_filter = ('platform', 'routing')
    inlines = [MatchParticipantInline]


@admin.register(MatchParticipant)
class MatchParticipantAdmin(admin.ModelAdmin):
    list_display = ('match', 'summoner_name', 'team_id', 'champion_name', 'kills', 'deaths', 'assists', 'win')
    search_fields = ('summoner_name', 'puuid', 'match__match_id')
    list_filter = ('win', 'team_id', 'champion_name')


@admin.register(MatchTimeline)
class MatchTimelineAdmin(admin.ModelAdmin):
    list_display = ('match', 'data_version', 'frame_interval', 'created_at')
    search_fields = ('match__match_id',)
    list_filter = ('data_version', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(PlayerYearlyStats)
class PlayerYearlyStatsAdmin(admin.ModelAdmin):
    list_display = ('summoner', 'year', 'platform', 'total_matches', 'wins', 'losses', 'win_rate', 'kda_ratio')
    search_fields = ('summoner__name', 'summoner__puuid')
    list_filter = ('year', 'platform', 'win_rate')
    readonly_fields = ('last_updated', 'created_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('summoner', 'year', 'platform')
        }),
        ('Match Counts', {
            'fields': ('total_matches', 'wins', 'losses')
        }),
        ('Aggregated Stats', {
            'fields': ('total_kills', 'total_deaths', 'total_assists', 'total_gold_earned',
                      'total_minions_killed', 'total_neutral_minions_killed', 'total_damage_to_champions')
        }),
        ('Diversity Stats', {
            'fields': ('unique_champions_played', 'most_played_champion', 'most_played_champion_count',
                      'unique_roles_played', 'unique_lanes_played')
        }),
        ('Calculated Stats', {
            'fields': ('win_rate', 'kda_ratio', 'average_kills', 'average_deaths', 'average_assists',
                      'average_gold_per_match', 'average_cs_per_match')
        }),
        ('Metadata', {
            'fields': ('last_updated', 'created_at'),
            'classes': ('collapse',)
        }),
    )

# Register your models here.
