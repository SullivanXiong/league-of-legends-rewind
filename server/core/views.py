from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Match, Summoner
from .riot_service import RiotApiClient
from .serializers import MatchSerializer, SummonerSerializer


class SummonerViewSet(viewsets.ModelViewSet):
    queryset = Summoner.objects.all().order_by('-last_updated')
    serializer_class = SummonerSerializer

    @action(detail=False, methods=['post'], url_path='lookup')
    def lookup(self, request):
        game_name = request.data.get('game_name')
        tag_line = request.data.get('tag_line')
        platform = request.data.get('platform', 'na1')
        routing = request.data.get('routing', 'americas')

        if not game_name or not tag_line:
            return Response({'detail': 'game_name and tag_line are required'}, status=status.HTTP_400_BAD_REQUEST)

        client = RiotApiClient(platform=platform, routing=routing)
        data = client.get_summoner_by_riot_id(game_name, tag_line)

        summoner, _ = Summoner.objects.update_or_create(
            puuid=data.get('puuid'),
            defaults={
                'summoner_id': data.get('gameName') or data.get('puuid'),
                'account_id': None,
                'name': data.get('gameName') or game_name,
                'tag_line': data.get('tagLine') or tag_line,
                'platform': platform,
                'routing': routing,
            }
        )

        return Response(self.get_serializer(summoner).data)


class MatchViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Match.objects.all().order_by('-created_at')
    serializer_class = MatchSerializer

    @action(detail=False, methods=['post'], url_path='sync')
    def sync(self, request):
        puuid = request.data.get('puuid')
        platform = request.data.get('platform', 'na1')
        routing = request.data.get('routing', 'americas')
        count = int(request.data.get('count', 5))

        if not puuid:
            return Response({'detail': 'puuid is required'}, status=status.HTTP_400_BAD_REQUEST)

        client = RiotApiClient(platform=platform, routing=routing)
        match_ids = client.get_match_ids_by_puuid(puuid, count=count)

        created = 0
        for match_id in match_ids:
            if Match.objects.filter(match_id=match_id).exists():
                continue
            raw = client.get_match(match_id)
            info = raw.get('info', {})
            meta = raw.get('metadata', {})

            match = Match.objects.create(
                match_id=match_id,
                data_version=meta.get('dataVersion'),
                game_creation=parse_datetime(str(info.get('gameCreation'))) if info.get('gameCreation') else None,
                game_duration=info.get('gameDuration'),
                queue_id=info.get('queueId'),
                platform=platform,
                routing=routing,
                raw=raw,
            )

            # Participants
            participants = info.get('participants', [])
            from .models import MatchParticipant, Summoner
            for p in participants:
                summoner = Summoner.objects.filter(puuid=p.get('puuid')).first()
                MatchParticipant.objects.create(
                    match=match,
                    summoner=summoner if summoner else Summoner.objects.create(
                        puuid=p.get('puuid'),
                        summoner_id=p.get('summonerId') or p.get('puuid'),
                        name=p.get('summonerName') or 'Unknown',
                        platform=platform,
                        routing=routing,
                    ),
                    puuid=p.get('puuid'),
                    summoner_name=p.get('summonerName') or '',
                    team_id=p.get('teamId') or 0,
                    champion_id=p.get('championId'),
                    champion_name=p.get('championName'),
                    role=p.get('role'),
                    lane=p.get('lane'),
                    kills=p.get('kills', 0),
                    deaths=p.get('deaths', 0),
                    assists=p.get('assists', 0),
                    win=bool(p.get('win', False)),
                    gold_earned=p.get('goldEarned', 0),
                    total_minions_killed=p.get('totalMinionsKilled', 0),
                    neutral_minions_killed=p.get('neutralMinionsKilled', 0),
                    damage_to_champions=p.get('totalDamageDealtToChampions', 0),
                    item0=p.get('item0'),
                    item1=p.get('item1'),
                    item2=p.get('item2'),
                    item3=p.get('item3'),
                    item4=p.get('item4'),
                    item5=p.get('item5'),
                    item6=p.get('item6'),
                    spell1=p.get('summoner1Id'),
                    spell2=p.get('summoner2Id'),
                    perk_primary_style=(p.get('perks', {}).get('styles') or [{}])[0].get('style'),
                    perk_sub_style=(p.get('perks', {}).get('styles') or [{}, {}])[1].get('style') if len((p.get('perks', {}).get('styles') or [])) > 1 else None,
                )
            created += 1

        return Response({'synced': created, 'requested': len(match_ids)})

    @action(detail=False, methods=['get'], url_path='by-puuid')
    def by_puuid(self, request):
        puuid = request.query_params.get('puuid')
        if not puuid:
            return Response({'detail': 'puuid is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            limit = int(request.query_params.get('limit', 20))
            offset = int(request.query_params.get('offset', 0))
        except ValueError:
            return Response({'detail': 'limit and offset must be integers'}, status=status.HTTP_400_BAD_REQUEST)

        qs = self.get_queryset().filter(participants__puuid=puuid).distinct()
        items = qs[offset:offset + limit]
        data = self.get_serializer(items, many=True).data
        return Response({
            'count': qs.count(),
            'limit': limit,
            'offset': offset,
            'results': data,
        })
