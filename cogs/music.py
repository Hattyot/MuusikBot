import discord.utils
import random
import math
import wavelink
import asyncio
import re
import config
import datetime
from discord.ext import commands
from modules import embed_maker, command, format_time, database

db = database.Connection()


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
        self.old_progress_bar = ''

        self.progress_bar_task = None

        self.wavelink_client = wavelink_client
        self.bot.loop.create_task(self.start_node())

    async def start_node(self):
        await self.bot.wait_until_ready()

        await self.wavelink_client.initiate_node(
            host='127.0.0.1',
            port=2333,
            rest_uri='http://127.0.0.1:2333',
            password='youshallnotpass',
            identifier=f'MuusikBot-{self.guild.id}',
            region=str(self.guild.region)
        )

    async def progress_bar(self, duration):
        self.old_progress_bar = ''
        current_position = 0
        formatted_duration_length = len(format_time.ms(duration, accuracy=3).split(' '))
        formatted_duration = format_time.ms(duration, accuracy=3, progress_bar=formatted_duration_length)

        part_duration = duration // 40
        equal_segments = [range(i * part_duration, (i + 1) * part_duration) for i in range(40)]

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

            line_str = list('-' * 40)
            line_str[position_index] = '●'
            line_str = ''.join(line_str)

            progress_bar_str = f'{formatted_position} |{line_str}| {formatted_duration}'

            if self.old_progress_bar == progress_bar_str:
                await asyncio.sleep(5)
                continue

            self.old_progress_bar = progress_bar_str

            await self.update_music_menu(current_progress=progress_bar_str)
            await asyncio.sleep(5)

    async def update_music_menu(self, page=0, queue_length=5, current_progress=None):
        if not self.music_menu:
            return

        if not current_progress:
            current_progress = self.old_progress_bar

        current_song = self.current_song

        if not page and not self.music_menu_page:
            page = 1
        elif not page and self.music_menu_page:
            page = self.music_menu_page

        self.music_menu_page = page

        queue_segment = self.queue[((page - 1) * queue_length):(page * queue_length)]

        if current_song:
            song_type = current_song.type
            link = current_song.uri if not current_song.ytid else f'http://y2u.be/{current_song.ytid}'
            currently_playing_str = f'**{song_type}:** [{current_song.title}]({link})'

            if song_type != 'Twitch':
                formatted_duration = format_time.ms(current_song.duration, accuracy=3)
                currently_playing_str += f' | `{formatted_duration}`'

            currently_playing_str += f' - <@{current_song.requester}>'

            if song_type != 'Twitch':
                if not current_progress:
                    if self.progress_bar_task:
                        self.progress_bar_task.cancel()
                    self.progress_bar_task = asyncio.create_task(self.progress_bar(current_song.duration))
                    return
                else:
                    currently_playing_str += f'\n{current_progress}'

        else:
            currently_playing_str = '\u200b'

        queue_str = []
        for i, song in enumerate(queue_segment):
            song_type = song.type
            link = song.uri if not song.ytid else f'http://y2u.be/{song.ytid}'

            value = f'`#{(i + 1) + 5 * (page - 1)}` - **{song_type}:** [{song.title}]({link})'

            if song_type != 'Twitch':
                formatted_duration = format_time.ms(song.duration, accuracy=3)
                value += f' | `{formatted_duration}`'
            value += f' - <@{song.requester}>'
            queue_str.append(value)

        queue_str = '\n'.join(queue_str) if queue_str else '\u200b'

        if len(queue_str) >= 1024:
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
        new_embed.set_field_at(0, name='Currently Playing:', value=currently_playing_str, inline=False)
        new_embed.set_field_at(1, name='Queue:', value=queue_str, inline=False)
        new_embed.set_footer(text=f'Page {page}/{page_count}')
        await self.music_menu.edit(embed=new_embed)

    async def process_song(self, query, requester):
        is_url = query.startswith('https://')
        is_playlist = is_url and '&list=' in query

        if is_url:
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

        if type(song) == list:
            if requester:
                song_list = [Song(s) for s in song]
            else:
                song_list = song
        else:
            song_list = [Song(song)]

        first_song = song_list.pop(0)

        if requester:
            first_song.requester = requester

            # add type data to song info
            for song in song_list:
                regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
                song.type = re.findall(regex, song.uri)[0].capitalize()

        if self.current_song is None:
            self.current_song = first_song
            self.old_progress_bar = ''
            if player.is_connected:
                await player.play(first_song)

        for s in song_list:
            if requester:
                s.requester = requester

            self.queue.append(s)

        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': [(self.current_song.id, self.current_song.requester)] + [(s.id, s.requester) for s in self.queue]}})

        return await self.update_music_menu()

    async def next(self):
        previous_song = self.queue[0] if self.queue else None
        if len(self.queue) == 0:
            db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': []}})
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
        self.queue = []
        db.dj.update_one({'guild_id': self.guild.id}, {'$set': {'playlist': [(self.current_song.id, self.current_song.requester)]}})
        await self.update_music_menu()


class Song:
    def __init__(self, song, song_type=None, requester=None):
        self.id = song.id
        self.info = song.info
        self.uri = song.uri
        self.ytid = song.ytid
        self.title = song.title
        self.duration = song.duration
        self.song_type = song_type
        self.requester = requester


class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot

    @wavelink.WavelinkMixin.listener()
    async def on_track_end(self, node, payload):
        player = payload.player
        playlist = self.bot.playlists[player.guild_id]

        previous_song = playlist.current_song

        playlist.old_progress_bar = ''
        if playlist.progress_bar_task:
            playlist.progress_bar_task.cancel()

        if payload.reason == 'FINISHED':
            # put the progress bar at the end and wait 2 seconds before the next song plays so it looks nicer
            formatted_duration_length = len(format_time.ms(previous_song.duration, accuracy=3).split(' '))
            formatted_position = format_time.ms(previous_song.duration, accuracy=3, progress_bar=formatted_duration_length)

            line_str = list('-' * 40)
            line_str[-1] = '●'
            line_str = ''.join(line_str)

            progress_bar_str = f'{formatted_position} |{line_str}| {formatted_position}'

            await playlist.update_music_menu(current_progress=progress_bar_str)
            await asyncio.sleep(2)

        playlist.current_song = None

        return await playlist.next()

    @commands.command(help='Change the volume of the bot', usage='volume [0-100]', examples=['volume 70'], clearance='User', cls=command.Command)
    async def volume(self, ctx, new_volume=None):
        if new_volume is None:
            return await embed_maker.command_error(ctx)

        if await self.check_voice(ctx):
            return

        if not new_volume.isdigit() or 100 < round(new_volume) < 1:
            return await embed_maker.message(ctx, 'Volume must be between **0** and **100**', colour='red')

        new_volume = round(new_volume)

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)
        await player.set_volume(new_volume)

        return await embed_maker.message(ctx, f'Volume has been changed to {new_volume}%', colour='green')

    @commands.command(help='Get the bot in a voice channel', usage='join', examples=['join'], clearance='User', cls=command.Command)
    async def join(self, ctx):
        if not ctx.author.voice:
            return await embed_maker.message(ctx, 'You need to be in a voice channel for me to join', colour='red'), 1

        voice_channel = ctx.author.voice.channel
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        try:
            await player.connect(voice_channel.id)
            return await embed_maker.message(ctx, f'Joined channel: **{voice_channel.name}**', colour='green', timestamp=None), 0
        except:
            return await embed_maker.message(ctx, 'Unable to connect to voice channel', colour='red', timestamp=None), 1

    @commands.command(help='Make the bot leave the voice channel', usage='leave', examples=['leave'], clearance='User', cls=command.Command)
    async def leave(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        playlist.current_song = None
        playlist.old_progress_bar = ''
        if playlist.progress_bar_task:
            playlist.progress_bar_task.cancel()

        await player.stop()
        await player.disconnect()

        return await ctx.message.add_reaction('👍')

    @commands.command(help='play a song from youtube', usage='play [song]', clearance='User', cls=command.Command,
                      examples=['play jack stauber buttercup', 'play https://www.youtube.com/watch?v=eYDI8b5Nn5s', 'play https://youtube.be/eYDI8b5Nn5s'])
    async def play(self, ctx, *, song_request=None):
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if song_request is None:
            if playlist.queue:
                await ctx.invoke(self.join)
                return await player.play(playlist.current_song)
            return await embed_maker.command_error(ctx)

        if not player.is_connected:
            _, error = await ctx.invoke(self.join)
            if error:
                return

        error = await playlist.process_song(song_request, ctx.author.id)
        if type(error) == str:
            return await embed_maker.message(ctx, error, colour='red')

    @commands.group(name='playlist', help='Manage saved playlist or save a playlist', usage='playlist [sub-command | page]',
                      examples=['playlist 2', 'playlist save electro swing', 'playlist delete electro swing', 'playlist get electro swing'],
                      sub_commands=['get', 'save', 'delete'], clearance='User', cls=command.Group)
    async def _playlist(self, ctx):
        if ctx.subcommand_passed is None:
            playlists_data = [*db.playlists.find({'guild_id': ctx.guild.id})][:10]
            pages = {1: ''}
            if not playlists_data:
                pages[1] = f'Currently there are no playlists saved'
            else:
                page = 1
                # generate topics string
                for i, playlist_obj in enumerate(playlists_data):
                    if i == 10:
                        page += 1
                    name = playlist_obj['name']
                    songs = playlist_obj['playlist']
                    saved_by = playlist_obj['saved_by']

                    pages[page] += f'**{name}** - <@{saved_by}>\n'
                    songs = [await self.bot.wavelink.build_track(s) for s, requester in songs[:5]]
                    pages[page] += ", ".join([f'**#{i + 1}** - `{s.title}`' for i, s in enumerate(songs)])
                    pages[page] += ' ...\n'

            embed = discord.Embed(title='Playlists', colour=config.EMBED_COLOUR, description=pages[1], timestamp=datetime.datetime.now())
            embed.set_footer(text=f'{ctx.author} - Page 1/{len(pages.keys())}', icon_url=ctx.author.avatar_url)

            return await ctx.channel.send(embed=embed)

    @_playlist.command(name='save', help='Save a playlist, so you can get this playlist again later', usage='playlist save [name]',
                      examples=['playlist save electro swing'], clearance='User', cls=command.Command)
    async def _playlist_save(self, ctx, *, name=None):
        if name is None:
            return await embed_maker.command_error(ctx)

        playlist = self.bot.playlists[ctx.guild.id]
        if len(playlist) < 5:
            return await embed_maker.message(ctx, 'Can\'t save a playlist with less than 5 songs')

        if len(name) > 30:
            return await embed_maker.message(ctx, 'playlist name cant be longer than 30 characters', colour='red')

        playlist_data = db.playlists.find_one({'guild_id': ctx.guild.id, 'name': name})
        if playlist_data:
            return await embed_maker.message(ctx, f'A playlist by the name `{name}` already exists', colour='red')

        db.playlists.insert_one(
            {
                'guild_id': ctx.guild.id,
                'name': name,
                'playlist': [(s.id, s.requester) for s in playlist.queue],
                'saved_by': ctx.author.id
            }
        )

        return await embed_maker.message(ctx, f'The current playlist has been saved under the name: `{name}`', colour='green')

    @_playlist.command(name='delete', help='Delete a playlist from the list of saved playlists', usage='playlist delete [name]',
                       examples=['playlist delete electro swing'], clearance='User', cls=command.Command)
    async def _playlist_delete(self, ctx, *, name=None):
        if name is None:
            return await embed_maker.command_error(ctx)

        if len(name) > 30:
            return await embed_maker.message(ctx, 'playlist name cant be longer than 30 characters')

        playlist_data = db.playlists.find_one({'guild_id': ctx.guild.id, 'name': name})
        if not playlist_data:
            return await embed_maker.message(ctx, f'Couldn\'t find a playlist by the name: `{name}`')

        db.playlists.delete_one({'guild_id': ctx.guild.id, 'name': name})

        return await embed_maker.message(ctx, f'Playlist `{name}` has been deleted')

    @_playlist.command(name='get', help='Get a saved playlist and append it to the current playlist',
                       usage='playlist get [name]',
                       examples=['playlist get electro swing'], clearance='User', cls=command.Command)
    async def _playlist_get(self, ctx, *, name=None):
        if name is None:
            return await embed_maker.command_error(ctx)

        playlist_data = db.playlists.find_one({'guild_id': ctx.guild.id, 'name': name})
        if not playlist_data:
            return await embed_maker.message(ctx, f'Couldn\'t find a playlist by the name: `{name}`')

        songs = playlist_data['playlist']
        tracks = []
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)
        if not playlist.queue and not player.is_connected:
            await ctx.invoke(self.join)

        for i, song in enumerate(songs):
            song_id, requester = song
            track = Song(await self.bot.wavelink.build_track(song_id), requester=requester)

            regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
            track.type = re.findall(regex, track.uri)[0].capitalize()

            tracks.append(track)

        return await playlist.add(tracks)

    @commands.command(help='search for a song', usage='search [query]', examples=['search jack stauber'], clearance='User', cls=command.Command)
    async def search(self, ctx, *, query=None):
        if query is None:
            return await embed_maker.command_error(ctx)

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if not player.is_connected:
            _, error = await ctx.invoke(self.join)
            if error:
                return

        wavelink_client = playlist.wavelink_client
        results = await wavelink_client.get_tracks(f'ytsearch:{query}', retry_on_failure=True)

        if not results:
            return await embed_maker.message(ctx, f"Couldn't find any matches for: {query}")

        search_str = ""
        for i, song in enumerate(results[:10]):
            formatted_duration = format_time.ms(song.duration, accuracy=3)
            search_str += f'`#{i + 1}` [{song.title}](http://y2u.be/{song.ytid}) - `{formatted_duration}`\n\n'

        search_str += '**Pick a song by typing its number.** Type cancel to exit.'
        search_msg = await embed_maker.message(ctx, search_str, nonce=10)

        check = lambda m: m.channel.id == ctx.channel.id and m.author.id == ctx.author.id
        try:
            msg = await self.bot.wait_for('message', check=check)
            content = msg.content
            if not content.isdigit() or int(content) < 1 or int(content) > 10:
                return await embed_maker.message(ctx, 'Invalid number', colour='red')

            song = results[int(content) - 1]
            await playlist.add(song, ctx.author.id)
            await search_msg.delete()
            await msg.delete()
        except asyncio.TimeoutError:
            await search_msg.delete()
            return await embed_maker.message(ctx, 'Search timeout.', colour='red')

    @commands.command(help='pause the bot', usage='pause', clearance='User', examples=['pause'], cls=command.Command)
    async def pause(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if player.is_paused:
            return await embed_maker.message(ctx, 'Bot is already paused', colour='red')

        await player.set_pause(True)
        return await ctx.message.add_reaction('👍')

    @commands.command(help='unpause the bot', usage='unpause', clearance='User', examples=['unpause'], cls=command.Command)
    async def unpause(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if not player.is_paused:
            return await embed_maker.message(ctx, 'Bot is already unpaused', colour='red')

        await player.set_pause(False)
        return await ctx.message.add_reaction('👍')

    @commands.command(help="remove the bot and clear its playlist", usage='stop', clearance='User', examples=['stop'],
                      cls=command.Command)
    async def stop(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]

        await ctx.invoke(self.leave)

        await playlist.clear()
        return await ctx.message.add_reaction('👍')

    @commands.command(help="skip a song on the playlist, requires 50% of people to vote for skip if non dj skips",
                      usage='skip', examples=['skip'], clearance='User', cls=command.Command)
    async def skip(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        await player.stop()

        return await ctx.message.add_reaction('👍')

    @commands.command(help="loop the playlist", usage='loop', examples=['loop'], clearance='User', cls=command.Command)
    async def loop(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        playlist.loop = True
        await playlist.update_music_menu()

        return await ctx.message.add_reaction('👍')

    @commands.command(help="shuffle the playlist", usage='shuffle', examples=['shuffle'], clearance='User', cls=command.Command)
    async def shuffle(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        await playlist.shuffle()

        return await ctx.message.add_reaction('👍')

    @commands.command(help='Clear the queue', usage='clear', examples=['clear'], clearance='User', cls=command.Command)
    async def clear(self, ctx):
        playlist = self.bot.playlists[ctx.guild.id]
        await playlist.clear()

        return await ctx.message.add_reaction('👍')

    @commands.command(help='Move to a page in the queue', usage='page [page num]', examples=['page 3'], clearance='User', cls=command.Command)
    async def page(self, ctx, page=None):
        if page is None:
            return await embed_maker.command_error(ctx)

        if await self.check_voice(ctx):
            return

        if not page.isdigit():
            return await embed_maker.message(ctx, 'Invalid page number', colour='red')

        playlist = self.bot.playlists[ctx.guild.id]
        page = int(page)
        pc = math.ceil(len(playlist) / 5)
        if pc < 1:
            pc = 1

        if page > pc or page < 1:
            page = 1

        await playlist.update_music_menu(page=int(page))

        return await ctx.message.add_reaction('👍')

    async def check_voice(self, ctx):
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if not player and not player.is_connected:
            return await embed_maker.message(ctx, "I'm not connected to any voice channel in this server", colour='red')

        if not ctx.author.voice or ctx.author.voice.channel.id != player.channel_id:
            return await embed_maker.message(ctx, "You are not in the same voice channel as the bot", colour='red')

    @commands.command(help='Sets up the music menu in a channel', usage='music_menu', examples=['music_menu'],
                      clearance='Mod', cls=command.Command)
    async def music_menu(self, ctx):
        channel = ctx.channel
        dj_data = db.dj.find_one({'guild_id': ctx.guild.id})
        if not dj_data:
            dj_data = {
                'guild_id': ctx.guild.id,
                'music_menu_channel_id': channel.id,
                'music_menu_message_id': 0,
            }
            db.dj.insert_one(dj_data)

        old_channel_id = dj_data['music_menu_channel_id']
        old_message_id = dj_data['music_menu_message_id']
        db.dj.update_one({'guild_id': ctx.guild.id}, {'$set': {'music_menu_channel_id': channel.id}})
        old_channel = ctx.guild.get_channel(old_channel_id)
        try:
            old_message = await old_channel.fetch_message(old_message_id)
            if old_message:
                await old_message.delete()
        except discord.HTTPException:
            pass

        menu_embed = discord.Embed(colour=config.EMBED_COLOUR)
        menu_embed.set_author(name='Playlist', icon_url=ctx.guild.icon_url)
        menu_embed.add_field(name='Currently Playing:', value='\u200b', inline=False)
        menu_embed.add_field(name='Queue:', value=f'\u200b\n\nSongs in queue: **0**\nPlaylist duration: **0ms**\nLoop: **True**', inline=False)
        menu_embed.set_footer(text='Page 1/1')
        menu_embed_msg = await ctx.send(embed=menu_embed, nonce=10)

        playlist = self.bot.playlists[ctx.guild.id]
        playlist.music_menu = menu_embed_msg

        db.dj.update_one({'guild_id': ctx.guild.id}, {'$set': {'music_menu_message_id': menu_embed_msg.id}})
        reactions = ['⏯', '⏩', '<:blank1:763115899099021323>', '🔄', '🔀', '<:blank2:763115938291253248>', '◀', '▶']
        for reaction in reactions:
            await menu_embed_msg.add_reaction(reaction)

        playlist = self.bot.playlists[ctx.guild.id]
        if playlist.queue:
            return await playlist.update_music_menu()


def setup(bot):
    bot.add_cog(Music(bot))
