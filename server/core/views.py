from django.utils.dateparse import parse_datetime
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Match, MatchTimeline, Summoner
from .riot_service import RiotApiClient
from .serializers import MatchSerializer, SummonerSerializer
from .tasks import recover_player_data, sync_player_data


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

    @action(detail=False, methods=['post'], url_path='sync-data')
    def sync_data(self, request):
        """
        Sync all data for a player using Celery workers.
        This endpoint accepts a player's game_name and tag_line, then spawns
        Celery workers to handle the data digestion process.
        """
        game_name = request.data.get('game_name')
        tag_line = request.data.get('tag_line')
        platform = request.data.get('platform', 'na1')
        routing = request.data.get('routing', 'americas')
        year = request.data.get('year')  # Optional, defaults to 2025 in task

        if not game_name or not tag_line:
            return Response(
                {'detail': 'game_name and tag_line are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate year if provided
        if year is not None:
            try:
                year = int(year)
                if year < 2020 or year > 2030:  # Reasonable bounds
                    return Response(
                        {'detail': 'year must be between 2020 and 2030'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'year must be a valid integer'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Start the Celery task
        task = sync_player_data.delay(
            game_name=game_name,
            tag_line=tag_line,
            platform=platform,
            routing=routing,
            year=year
        )

        return Response({
            'task_id': task.id,
            'status': 'started',
            'message': f'Data sync started for {game_name}#{tag_line}',
            'platform': platform,
            'routing': routing,
            'year': year or 'default (2025)'
        }, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['get'], url_path='task-status')
    def task_status(self, request):
        """
        Check the status of a Celery task with real-time database information.
        """
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response(
                {'detail': 'task_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        from celery.result import AsyncResult
        task_result = AsyncResult(task_id)
        
        response_data = {
            'task_id': task_id,
            'status': task_result.status,
        }
        
        # Get real-time database information
        try:
            # Try to get summoner info from the task result
            summoner_name = None
            summoner_tag = None
            year = None
            
            if task_result.status == 'SUCCESS' and task_result.result:
                result_data = task_result.result
                summoner_name = result_data.get('summoner_name')
                year = result_data.get('year')
            elif task_result.status == 'PROGRESS' and task_result.info:
                progress_data = task_result.info
                summoner_name = progress_data.get('summoner_name')
                year = progress_data.get('year')
            
            # If we have summoner info, get real-time database stats
            if summoner_name:
                from django.db.models import Count
                from .models import Match, MatchParticipant, PlayerYearlyStats
                
                # Find the summoner
                summoner = Summoner.objects.filter(name__iexact=summoner_name).first()
                if summoner:
                    # Get real-time match count
                    total_matches_in_db = Match.objects.filter(
                        participants__puuid=summoner.puuid
                    ).distinct().count()
                    
                    # Get real-time yearly stats
                    yearly_stats = PlayerYearlyStats.objects.filter(
                        summoner=summoner,
                        year=year or 2025
                    ).first()
                    
                    response_data.update({
                        'summoner_name': summoner.name,
                        'summoner_tag': summoner.tag_line,
                        'year': year or 2025,
                        'real_time_stats': {
                            'total_matches_in_database': total_matches_in_db,
                            'yearly_stats': {
                                'total_matches': yearly_stats.total_matches if yearly_stats else 0,
                                'wins': yearly_stats.wins if yearly_stats else 0,
                                'losses': yearly_stats.losses if yearly_stats else 0,
                                'win_rate': yearly_stats.win_rate if yearly_stats else 0.0,
                            } if yearly_stats else None
                        }
                    })
        
        except Exception as e:
            # If there's an error getting real-time data, just continue with basic info
            response_data['real_time_error'] = str(e)
        
        # Add the original task result info
        if task_result.status == 'PROGRESS':
            response_data.update(task_result.info)
        elif task_result.status == 'SUCCESS':
            response_data.update(task_result.result)
        elif task_result.status == 'FAILURE':
            response_data['error'] = str(task_result.info)
        
        return Response(response_data)

    @action(detail=False, methods=['get'], url_path='database-status')
    def database_status(self, request):
        """
        Get real-time database status for a summoner.
        """
        game_name = request.query_params.get('game_name')
        tag_line = request.query_params.get('tag_line')
        year = request.query_params.get('year', 2025)
        
        if not game_name or not tag_line:
            return Response(
                {'detail': 'game_name and tag_line are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            year = int(year)
        except (ValueError, TypeError):
            return Response(
                {'detail': 'year must be a valid integer'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            from django.db.models import Count
            from .models import Match, MatchParticipant, PlayerYearlyStats
            
            # Find the summoner
            summoner = Summoner.objects.filter(
                name__iexact=game_name,
                tag_line__iexact=tag_line
            ).first()
            
            if not summoner:
                return Response({
                    'summoner_name': game_name,
                    'summoner_tag': tag_line,
                    'year': year,
                    'status': 'not_found',
                    'message': 'Summoner not found in database'
                })
            
            # Get real-time match count
            total_matches_in_db = Match.objects.filter(
                participants__puuid=summoner.puuid
            ).distinct().count()
            
            # Get real-time yearly stats
            yearly_stats = PlayerYearlyStats.objects.filter(
                summoner=summoner,
                year=year
            ).first()
            
            # Get matches from this year specifically
            year_matches = Match.objects.filter(
                participants__puuid=summoner.puuid,
                game_creation__year=year
            ).distinct().count()
            
            response_data = {
                'summoner_name': summoner.name,
                'summoner_tag': summoner.tag_line,
                'summoner_puuid': summoner.puuid,
                'year': year,
                'status': 'found',
                'real_time_stats': {
                    'total_matches_in_database': total_matches_in_db,
                    'matches_from_year': year_matches,
                    'yearly_stats': {
                        'total_matches': yearly_stats.total_matches if yearly_stats else 0,
                        'wins': yearly_stats.wins if yearly_stats else 0,
                        'losses': yearly_stats.losses if yearly_stats else 0,
                        'win_rate': yearly_stats.win_rate if yearly_stats else 0.0,
                        'kda_ratio': yearly_stats.kda_ratio if yearly_stats else 0.0,
                        'most_played_champion': yearly_stats.most_played_champion if yearly_stats else None,
                    } if yearly_stats else None
                }
            }
            
            return Response(response_data)
            
        except Exception as e:
            return Response({
                'error': f'Database error: {str(e)}',
                'summoner_name': game_name,
                'summoner_tag': tag_line,
                'year': year
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='recover-data')
    def recover_data(self, request):
        """
        Rsync-like recovery endpoint that can resume from where it left off.
        This endpoint checks what data already exists and only processes missing data.
        """
        game_name = request.data.get('game_name')
        tag_line = request.data.get('tag_line')
        platform = request.data.get('platform', 'na1')
        routing = request.data.get('routing', 'americas')
        year = request.data.get('year')  # Optional, defaults to 2025 in task

        if not game_name or not tag_line:
            return Response(
                {'detail': 'game_name and tag_line are required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validate year if provided
        if year is not None:
            try:
                year = int(year)
                if year < 2020 or year > 2030:  # Reasonable bounds
                    return Response(
                        {'detail': 'year must be between 2020 and 2030'}, 
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'year must be a valid integer'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Start the recovery task
        task = recover_player_data.delay(
            game_name=game_name,
            tag_line=tag_line,
            platform=platform,
            routing=routing,
            year=year
        )

        return Response({
            'task_id': task.id,
            'status': 'started',
            'message': f'Data recovery started for {game_name}#{tag_line}',
            'platform': platform,
            'routing': routing,
            'year': year or 'default (2025)',
            'recovery_mode': True
        }, status=status.HTTP_202_ACCEPTED)


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

    @action(detail=True, methods=['post'], url_path='sync-timeline')
    def sync_timeline(self, request, pk=None):
        """Sync timeline data for a specific match"""
        match = self.get_object()
        
        if hasattr(match, 'timeline'):
            return Response({'detail': 'Timeline already exists for this match'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            client = RiotApiClient(platform=match.platform, routing=match.routing)
            timeline_data = client.get_match_timeline(match.match_id)
            
            # Extract metadata from timeline data
            metadata = timeline_data.get('metadata', {})
            info = timeline_data.get('info', {})
            
            MatchTimeline.objects.create(
                match=match,
                data_version=metadata.get('dataVersion'),
                frame_interval=info.get('frameInterval'),
                raw=timeline_data,
            )
            
            return Response({'detail': 'Timeline synced successfully'})
            
        except Exception as e:
            return Response({'detail': f'Failed to sync timeline: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='sync-timelines')
    def sync_timelines(self, request):
        """Sync timeline data for multiple matches"""
        match_ids = request.data.get('match_ids', [])
        platform = request.data.get('platform', 'na1')
        routing = request.data.get('routing', 'americas')
        
        if not match_ids:
            return Response({'detail': 'match_ids is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not isinstance(match_ids, list):
            return Response({'detail': 'match_ids must be a list'}, status=status.HTTP_400_BAD_REQUEST)
        
        client = RiotApiClient(platform=platform, routing=routing)
        synced = 0
        errors = []
        
        for match_id in match_ids:
            try:
                match = Match.objects.filter(match_id=match_id).first()
                if not match:
                    errors.append(f'Match {match_id} not found')
                    continue
                
                if hasattr(match, 'timeline'):
                    errors.append(f'Timeline already exists for match {match_id}')
                    continue
                
                timeline_data = client.get_match_timeline(match_id)
                metadata = timeline_data.get('metadata', {})
                info = timeline_data.get('info', {})
                
                MatchTimeline.objects.create(
                    match=match,
                    data_version=metadata.get('dataVersion'),
                    frame_interval=info.get('frameInterval'),
                    raw=timeline_data,
                )
                synced += 1
                
            except Exception as e:
                errors.append(f'Failed to sync timeline for {match_id}: {str(e)}')
        
        return Response({
            'synced': synced,
            'requested': len(match_ids),
            'errors': errors
        })
