import base64
import time
import re
import asyncio
import requests
from modules import Playlist


class SpotifyLink:
    def __init__(self, client_id, client_secret, wavelink_client):
        self.client_id = client_id
        self.client_secret = client_secret
        self.wavelink_client = wavelink_client

        self.token = ""
        self.token_expire = 0

    async def _renew_spotify_token(self):
        url = "https://accounts.spotify.com/api/token"
        auth = base64.b64encode(f'{self.client_id}:{self.client_secret}'.encode('ascii')).decode('ascii')
        headers = {'Authorization': f'Basic {auth}'}
        data = {'grant_type': "client_credentials"}
        response = requests.post(url, headers=headers, data=data)
        response_json = response.json()

        self.token = response_json['access_token']
        self.token_expire = time.time() + response_json['expires_in']

    async def process_spotify_url(self, url):
        type = re.findall(r'https://open.spotify.com/(track|playlist|album)/', url)
        type = 'track' if not type else type[0]

        id = re.findall(rf'https://open.spotify.com/{type}/(.*)', url)
        if not id:
            return None

        id = id[0].strip()

        if self.token_expire <= time.time():
            await self._renew_spotify_token()
            if not self.token or self.token_expire <= time.time():
                return None

        headers = {'Authorization': f'Bearer {self.token}'}
        url = f'https://api.spotify.com/v1/{type}s/{id}'
        if type == 'playlist' or type == 'album':
            url += '/tracks?offset=0&limit=250'

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return None

        response = response.json()

        if type == 'playlist' or type == 'album':
            if 'tracks' not in response or not response['tracks']:
                return None

            track_list = response['tracks']['items']
            futures = []
            tracks = [0] * len(track_list)

            for i, track in enumerate(track_list):
                track_obj = track['track'] if type == 'playlist' else track
                future = asyncio.create_task(self.fetch_track(i, track_obj, tracks))
                futures.append(future)

            if futures:
                await asyncio.gather(*futures)

            return [s for s in tracks if s]

        elif type == 'track':
            tracks = [0]
            await self.fetch_track(0, response, tracks)
            return tracks

    async def fetch_track(self, index, track, tracks):
        track_name = track["name"]
        track_artists = [track["artists"][i]["name"] for i in range(len(track["artists"]))]
        track_obj = await self.wavelink_client.get_tracks(f'ytsearch:{track_name} - {", ".join(track_artists)}', retry_on_failure=True)
        if track_obj:
            # search for song where duration difference is less than 1 min
            for t in track_obj:
                if abs(int(track['duration_ms']) - int(t.duration)) < 60 * 1000:
                    song_obj = Playlist.Song(t)
                    song_obj.custom_title = f'{track_name} - {track_artists[0]}'
                    tracks[index] = song_obj
                    return
