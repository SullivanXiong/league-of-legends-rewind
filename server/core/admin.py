from django.contrib import admin

from .models import Match, MatchParticipant, Summoner


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

# Register your models here.
