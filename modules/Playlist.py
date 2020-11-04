import random
import math
import config
import wavelink
import re
import time
import asyncio
from youtube_title_parse import get_artist_title
from modules import format_time, database
from .spotify_link import SpotifyLink

db = database.Connection()


class Song(wavelink.Track):
    def __init__(self, song, song_type=None, requester=None):
        self.custom_title = None
        self.type = song_type
        self.requester = requester
        super().__init__(song.id, song.info, song.query)

    @property
    def title(self):
        return self._title if not self.custom_title else self.custom_title

    @title.setter
    def title(self, value):
        self._title = value


class Playlist:
    def __init__(self, bot, guild, wavelink_client):
        self.bot = bot
        self.guild = guild
        self.current_song = None

        self.history = []

        self.queue = []
        self.loop = False

        self.music_menu = None

        self.music_menu_page = 1
        self.old_progress_bar = None
        self.progress_bar_task = None

        self.wavelink_client = wavelink_client
        self.bot.loop.create_task(self.start_node())

        self.spotify_parser = SpotifyLink(config.SPOTIFY_CLIENT_ID, config.SPOTIFY_CLIENT_SECRET, self.wavelink_client)

    async def progress_bar(self, duration):
        self.old_progress_bar = ''
        current_position = 0
        formatted_duration_length = len(format_time.ms(duration, accuracy=3).split(' '))
        formatted_duration = format_time.ms(duration, accuracy=3, progress_bar=formatted_duration_length)

        parts = 25
        part_duration = duration // parts
        equal_segments = [range(i * part_duration, (i + 1) * part_duration) for i in range(parts)]

        player = self.wavelink_client.get_player(self.guild.id)

        while current_position < duration:
            if player.is_paused:
                await asyncio.sleep(5)
                continue

            current_position = 5000 * round(player.position / 5000)

            pos_range = [r for r in equal_segments if current_position in r]
            if not pos_range:
                return

            position_index = equal_segments.index(pos_range[0])
            formatted_position = format_time.ms(current_position, accuracy=3, progress_bar=formatted_duration_length)

            line_str = '■' * position_index + '—' * (parts - position_index)
            progress_bar_str = f'`{formatted_position} [{line_str}] {formatted_duration}`'

            if self.old_progress_bar == progress_bar_str:
                await asyncio.sleep(5)
                continue

            self.old_progress_bar = progress_bar_str

            await self.update_music_menu(current_progress=progress_bar_str)
            await asyncio.sleep(5)

    async def start_node(self):
        await self.bot.wait_until_ready()

        node = self.wavelink_client.get_node(f'MuusikBot-{self.guild.id}')
        if node:
            return

        await self.wavelink_client.initiate_node(
            host=f'{config.LAVALINK_HOST}',
            port=2333,
            rest_uri=f'http://{config.LAVALINK_HOST}:2333',
            password='youshallnotpass',
            identifier=f'MuusikBot-{self.guild.id}',
            region=str(self.guild.region)
        )

    async def update_music_menu(self, page=0, current_progress=''):
        if not self.music_menu:
            return

        player = self.wavelink_client.get_player(self.guild.id)

        if not page and not self.music_menu_page:
            page = 1
        elif not page and self.music_menu_page:
            page = self.music_menu_page

        self.music_menu_page = page

        music_menu_str = '**Currently Playing:**\n'

        if not current_progress:
            current_progress = self.old_progress_bar

        if self.current_song:
            if not self.current_song.custom_title:
                result = get_artist_title(self.current_song.title)
                if result:
                    title = f'{result[0]} - {result[1]}'
                else:
                    title = self.current_song.title
            else:
                title = self.current_song.title

            song_type = self.current_song.type
            currently_playing_str = f'**{song_type}:** ' if song_type != 'Youtube' else ''
            currently_playing_str += f'[{title}]({self.current_song.uri})'

            if song_type != 'Twitch':
                formatted_duration = format_time.ms(self.current_song.duration, accuracy=3)
                currently_playing_str += f' | `{formatted_duration}`'

            user = self.bot.get_user(self.current_song.requester)
            if not user:
                try:
                    user = await self.bot.fetch_user(self.current_song.requester)
                except:
                    pass

            if user:
                name = user.display_name if len(user.display_name) <= 13 else f'{user.display_name[:13]}...'
                currently_playing_str += f' - *{name}*'

            if song_type != 'Twitch':
                if not current_progress:
                    if self.progress_bar_task:
                        self.progress_bar_task.cancel()
                    self.progress_bar_task = asyncio.create_task(self.progress_bar(self.current_song.duration))
                    return
                else:
                    currently_playing_str += f'\n{current_progress}'

            music_menu_str += f'{currently_playing_str}\n\n'
        else:
            music_menu_str += '\n'

        music_menu_str += '**Queue:**\n'

        queue_str = []
        for i, song in enumerate(self.queue[10 * (page - 1):10 * page]):
            if not song.custom_title:
                result = get_artist_title(song.title)
                if result:
                    title = f'{result[0]} - {result[1]}'
                else:
                    title = song.title
            else:
                title = song.title

            value = f'`#{(i + 1) + 10 * (page - 1)}` - '
            value += f'**{song.type}:** ' if song.type != 'Youtube' else ''
            value += f'[{title}]({song.uri})'

            if song.type != 'Twitch':
                formatted_duration = format_time.ms(song.duration, accuracy=3)
                value += f' | `{formatted_duration}`'

            user = self.bot.get_user(self.current_song.requester)
            if not user:
                try:
                    user = await self.bot.fetch_user(self.current_song.requester)
                except:
                    pass

            if user:
                name = user.display_name if len(user.display_name) <= 13 else f'{user.display_name[:13]}...'
                value += f' - *{name}*'

            queue_str.append(value)

        music_menu_str += '\n'.join(queue_str) if queue_str else '\u200b'

        total_duration = sum([s.duration for s in self.queue])

        total_duration_formatted = format_time.ms(total_duration, accuracy=4)
        if self.current_song and self.current_song.type == 'Twitch':
            total_duration_formatted = '∞'

        music_menu_str += f'\n\nSongs in queue: **{len(self)}**\nPlaylist duration: **{total_duration_formatted}**\nLoop: **{self.loop}**'

        page_count = math.ceil(len(self) / 10)
        if page_count == 0:
            page_count = 1

        author_name = 'Playlist' + (' - Paused' if player.is_paused or not player.is_connected else '')

        new_embed = self.music_menu.embeds[0]
        new_embed.set_author(name=author_name, icon_url=self.guild.icon_url)
        new_embed.description = music_menu_str
        new_embed.set_footer(text=f'Page {page}/{page_count}')
        await self.music_menu.edit(embed=new_embed)
        return True

    async def process_song(self, query, requester):
        is_url = query.startswith('https://')
        is_playlist = is_url and '&list=' in query

        if is_url:
            if 'https://open.spotify.com' in query and config.SPOTIFY_CLIENT_ID:
                spotify_tracks = await self.spotify_parser.process_spotify_url(query)
                if not spotify_tracks:
                    return 'Unable to get tracks from spotify url'

                return await self.add(spotify_tracks, requester)

            songs_data = await self.wavelink_client.get_tracks(f'{query}', retry_on_failure=True)
            if not songs_data:
                return f"Invalid url: {query}"

            if is_playlist:
                return await self.add(songs_data.tracks, requester)

            song = songs_data[0]
        else:
            songs_data = await self.wavelink_client.get_tracks(f'ytsearch:{query}', retry_on_failure=True)

            if not songs_data:
                return f"Couldn't find any matches for: {query}"

            song = songs_data[0]

        await self.add(song, requester)
        await self.update_music_menu()

    def __len__(self):
        return len(self.queue)

    async def add(self, song, requester=None):
        player = self.wavelink_client.get_player(self.guild.id)
        db.timers.delete_one({'guild_id': self.guild.id, 'event': 'leave_vc'})
        if type(song) == list:
            if type(song[0]) != Song:
                song_list = [Song(s) for s in song]
            else:
                song_list = song
        elif type(song) == Song:
            song_list = [song]
        else:
            song_list = [Song(song)]

        for s in song_list:
            regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
            s.type = re.findall(regex, s.uri)[0].capitalize()
            s.requester = requester

        first_song = song_list.pop(0)

        if self.current_song is None:
            self.current_song = first_song
            self.old_progress_bar = ''
            if player.is_connected:
                await player.play(first_song)

        self.queue += song_list
        self.update_dj_db()
        return await self.update_music_menu()

    def update_dj_db(self):
        playlist = [(self.current_song.id, self.current_song.requester, self.current_song.custom_title)] if self.current_song else []
        playlist += [(s.id, s.requester, s.custom_title) for s in self.queue]

        history = [(s.id, s.requester, s.custom_title) for s in self.history]
        print(len(playlist))
        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': playlist, 'history': history}})

    def add_to_history(self, songs: list):
        for song in songs:
            self.history.append(song)
            if len(self.history) > 20:
                del self.history[0]

    async def next(self):
        previous_song = self.history[-1] if self.history else None
        if len(self.queue) == 0:
            self.update_dj_db()

            # start 5 min timer to leave vc
            utils_cog = self.bot.get_cog('Utils')
            await utils_cog.create_timer(guild_id=self.guild.id, expires=round(time.time()) + 300, event='leave_vc')

            await self.update_music_menu()
            return None

        if self.loop:
            self.queue.append(previous_song)

        next_song = self.queue.pop(0)
        self.current_song = next_song
        self.update_dj_db()
        await self.update_music_menu()

        player = self.wavelink_client.get_player(self.guild.id)
        await player.play(next_song)

    async def shuffle(self):
        first = [self.queue[0]]
        to_shuffle = self.queue[1:]
        random.shuffle(to_shuffle)
        self.queue = first + to_shuffle

        self.update_dj_db()
        await self.update_music_menu()

    async def clear(self):
        self.current_song = None
        self.queue = []
        self.history = []
        self.update_dj_db()
        await self.update_music_menu()

    async def clear_queue(self):
        self.queue = []
        self.update_dj_db()
        await self.update_music_menu()
