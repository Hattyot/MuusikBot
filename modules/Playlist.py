import random
import math
import config
import wavelink
import re
import time
from modules import format_time, database
from .spotify_link import SpotifyLink

db = database.Connection()


class Song(wavelink.Track):
    def __init__(self, song, song_type=None, requester=None):
        super().__init__(song.id, song.info, song.query)
        self.type = song_type
        self.requester = requester


class Playlist:
    def __init__(self, bot, guild, wavelink_client):
        self.bot = bot
        self.guild = guild
        self.current_song = None

        self.queue = []
        self.loop = False

        self.music_menu = None

        self.old_queue_str = '\u200b'
        self.old_currently_playing_str = '\u200b'
        self.old_page_count = 1
        self.music_menu_page = 1

        self.wavelink_client = wavelink_client
        self.bot.loop.create_task(self.start_node())

        self.spotify_parser = SpotifyLink(config.SPOTIFY_CLIENT_ID, config.SPOTIFY_CLIENT_SECRET, self.wavelink_client)

    async def start_node(self):
        await self.bot.wait_until_ready()

        await self.wavelink_client.initiate_node(
            host=f'{config.LAVALINK_HOST}',
            port=8080,
            rest_uri=f'http://{config.LAVALINK_HOST}:8080',
            password='youshallnotpass',
            identifier=f'MuusikBot-{self.guild.id}',
            region=str(self.guild.region)
        )

    async def update_music_menu(self, page=0, queue_length=8):
        if not self.music_menu:
            return

        player = self.wavelink_client.get_player(self.guild.id)

        if not page and not self.music_menu_page:
            page = 1
        elif not page and self.music_menu_page:
            page = self.music_menu_page

        self.music_menu_page = page

        queue_segment = self.queue[((page - 1) * queue_length):(page * queue_length)]

        if self.current_song:
            song_type = self.current_song.type
            currently_playing_str = f'**{song_type}:** ' if song_type != 'Youtube' else ''
            currently_playing_str += f'[{self.current_song.title}]({self.current_song.uri})'

            if song_type != 'Twitch':
                formatted_duration = format_time.ms(self.current_song.duration, accuracy=3)
                currently_playing_str += f' | `{formatted_duration}`'

            currently_playing_str += f' - <@{self.current_song.requester}>'
        else:
            currently_playing_str = '\u200b'

        queue_str = []
        for i, song in enumerate(queue_segment):
            song_type = song.type
            value = f'`#{(i + 1) + 5 * (page - 1)}` - '
            value += f'**{song_type}:** ' if song_type != 'Youtube' else ''
            value += f'[{song.title}]({song.uri})'

            if song_type != 'Twitch':
                formatted_duration = format_time.ms(song.duration, accuracy=3)
                value += f' | `{formatted_duration}`'
            value += f' - <@{song.requester}>'
            queue_str.append(value)

        queue_str = '\n'.join(queue_str) if queue_str else '\u200b'

        if len(queue_str) >= 950:
            return await self.update_music_menu(page, queue_length-1)

        if not queue_str:
            queue_str = self.old_queue_str

        if not currently_playing_str:
            currently_playing_str = self.old_currently_playing_str

        page_count = math.ceil(len(self) / queue_length)
        if page_count == 0:
            page_count = 1

        self.old_queue_str = queue_str
        self.old_currently_playing_str = currently_playing_str
        self.old_page_count = page_count

        total_duration = sum([s.duration for s in self.queue])

        total_duration_formatted = format_time.ms(total_duration, accuracy=4)
        if self.current_song and self.current_song.type == 'Twitch':
            total_duration_formatted = '∞'

        queue_str += f'\n\nSongs in queue: **{len(self)}**\nPlaylist duration: **{total_duration_formatted}**\nLoop: **{self.loop}**'

        new_embed = self.music_menu.embeds[0]

        if self.current_song and new_embed.thumbnail != self.current_song.thumb:
            new_embed.set_thumbnail(url=self.current_song.thumb)
        elif not self.current_song:
            new_embed.set_thumbnail(url='')

        author_name = 'Playlist' + (' - Paused' if player.is_paused or not player.is_connected else '')
        new_embed.set_author(name=author_name, icon_url=self.guild.icon_url)
        new_embed.set_field_at(0, name='Currently Playing:', value=currently_playing_str, inline=False)
        new_embed.set_field_at(1, name='Queue:', value=queue_str, inline=False)
        new_embed.set_footer(text=f'Page {page}/{page_count}')
        await self.music_menu.edit(embed=new_embed)
        return True

    async def process_song(self, query, requester):
        is_url = query.startswith('https://')
        is_playlist = is_url and '&list=' in query

        if is_url:
            if 'https://open.spotify.com' in query:
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
            if requester:
                song_list = [Song(s) for s in song]
            else:
                song_list = song
        elif not requester:
            song_list = [song]
        else:
            song_list = [Song(song)]

        if requester:
            for s in song_list:
                regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
                s.type = re.findall(regex, s.uri)[0].capitalize()
                s.requester = requester

        first_song = song_list.pop(0)

        if self.current_song is None:
            self.current_song = first_song
            # self.old_progress_bar = ''
            if player.is_connected:
                await player.play(first_song)

        self.queue += song_list

        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': [(self.current_song.id, self.current_song.requester)] + [(s.id, s.requester) for s in self.queue]}})

        return await self.update_music_menu()

    async def next(self):
        previous_song = self.queue[0] if self.queue else None
        if len(self.queue) == 0:
            db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': []}})

            # start 5 min timer to leave vc
            utils_cog = self.bot.get_cog('Utils')
            await utils_cog.create_timer(guild_id=self.guild.id, expires=round(time.time()) + 300, event='leave_vc')

            await self.update_music_menu()
            return None

        if self.loop:
            self.queue.append(previous_song)

        next_song = self.queue.pop(0)
        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': [(next_song.id, next_song.requester)] + [(s.id, s.requester) for s in self.queue]}})
        self.current_song = next_song
        await self.update_music_menu()

        player = self.wavelink_client.get_player(self.guild.id)
        await player.play(next_song)

    async def shuffle(self):
        first = [self.queue[0]]
        to_shuffle = self.queue[1:]
        random.shuffle(to_shuffle)
        self.queue = first + to_shuffle

        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': [(self.current_song.id, self.current_song.requester)] + [(s.id, s.requester) for s in self.queue]}})
        await self.update_music_menu()

    async def clear(self):
        self.current_song = None
        self.queue = []
        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': []}})
        await self.update_music_menu()

    async def clear_queue(self):
        self.queue = []
        pl = [(self.current_song.id, self.current_song.requester)] if self.current_song else []
        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': pl}})
        await self.update_music_menu()
