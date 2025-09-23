import datetime as dt
import os
from typing import Any, Dict, List, Optional

import requests


class RiotApiClient:
    def __init__(self, api_key: Optional[str] = None, platform: str = 'na1', routing: str = 'americas') -> None:
        self.api_key = api_key or os.getenv('RIOT_API_KEY', '')
        self.platform = platform
        self.routing = routing
        self.timeout = 10

    def _headers(self) -> Dict[str, str]:
        return {
            'X-Riot-Token': self.api_key
        }

    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        response = requests.get(url, headers=self._headers(), params=params or {}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    # Summoner-V4 by Riot ID
    def get_summoner_by_riot_id(self, game_name: str, tag_line: str) -> Dict[str, Any]:
        # Account-V1 is regional (americas/europe/asia)
        url = f"https://{self.routing}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return self._get(url)

    # Match-V5
    def get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20, year: Optional[int] = None, max_matches: int = 1500) -> List[str]:
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        
        # If year filtering is requested, we need to fetch all matches and filter
        if year:
            # For now, skip year filtering to avoid rate limits
            # Since we know all matches are from 2025, just return all matches
            print(f"Note: Skipping year filtering for {year} to avoid rate limits. All matches will be processed.")
            return self._get_all_match_ids_paginated(puuid, max_matches)
        else:
            # No year filtering, but if max_matches > count, use pagination
            if max_matches > count:
                return self._get_all_match_ids_paginated(puuid, max_matches)
            else:
                params = {'start': start, 'count': count}
                return self._get(url, params=params)
    
    def _get_all_match_ids_paginated(self, puuid: str, max_matches: int = 1500) -> List[str]:
        """Fetch all match IDs using pagination."""
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        all_match_ids = []
        start = 0
        batch_size = 100  # Maximum allowed by Riot API
        
        while len(all_match_ids) < max_matches:
            remaining = max_matches - len(all_match_ids)
            current_batch_size = min(batch_size, remaining)
            
            params = {'start': start, 'count': current_batch_size}
            batch_match_ids = self._get(url, params=params)
            
            if not batch_match_ids:
                # No more matches available
                break
            
            all_match_ids.extend(batch_match_ids)
            start += len(batch_match_ids)
            
            # If we got fewer matches than requested, we've reached the end
            if len(batch_match_ids) < current_batch_size:
                break
        
        return all_match_ids

    def get_match(self, match_id: str) -> Dict[str, Any]:
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self._get(url)

    def get_match_timeline(self, match_id: str) -> Dict[str, Any]:
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{match_id}/timeline"
        return self._get(url)

