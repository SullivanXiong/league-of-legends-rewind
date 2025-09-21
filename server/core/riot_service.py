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
    def get_match_ids_by_puuid(self, puuid: str, start: int = 0, count: int = 20) -> List[str]:
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        params = {'start': start, 'count': count}
        return self._get(url, params=params)

    def get_match(self, match_id: str) -> Dict[str, Any]:
        url = f"https://{self.routing}.api.riotgames.com/lol/match/v5/matches/{match_id}"
        return self._get(url)

