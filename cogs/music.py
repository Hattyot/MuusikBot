import discord.utils
import random
import time
import math
import wavelink
from config import EMBED_COLOUR
from discord.ext import commands
from modules import embed_maker, command, format_time, database

db = database.Connection()


class Playlist:
    def __init__(self, bot, guild):
        # Stores the links os the songs in queue and the ones already played
        self.queue = []
        self.loop = False
        self.loop_counter = 0
        self.bot = bot
        self.guild = guild
        self.current_song = None

        self.old_queue_str = '\u200b'
        self.old_currently_playing_str = '\u200b'
        self.old_page_count = 1
        self.music_menu_page = 1

        self.music_menu = None

        self.wavelink = wavelink.Client(bot=self.bot)
        self.bot.loop.create_task(self.start_node())

    async def start_node(self):
        await self.bot.wait_until_ready()

        await self.wavelink.initiate_node(
            host='127.0.0.1',
            port=2333,
            rest_uri='http://0.0.0.0:2333',
            password='youshallnotpass',
            identifier='TEST',
            region='eu'
        )

    async def update_music_menu(self, to_update=None, page=1):
        queue_str = ''
        currently_playing_str = ''
        current_song = self.current_song

        queue_segment = self.queue[((page - 1) * 10) + 1:(page * 10) + 1]
        self.music_menu_page = page

        if to_update is None or to_update == 'currently playing':
            if current_song:
                formatted_duration = format_time.ms(current_song.duration, accuracy=3)
                currently_playing_str = f'[{current_song.title}](http://y2u.be/{current_song.ytid}) | `{formatted_duration}` - <@{current_song.info["requester"]}>'
            else:
                currently_playing_str = '\u200b'

        if to_update is None or to_update == 'queue':
            queue_str = []
            for i, song in enumerate(queue_segment):
                formatted_duration = format_time.ms(song.duration, accuracy=3)
                value = f'`#{i + 1}` - [{song.title}](http://y2u.be/{song.ytid}) | `{formatted_duration}` - <@{song.info["requester"]}>'
                queue_str.append(value)
            queue_str = '\n'.join(queue_str) if queue_str else '\u200b'

        if not queue_str:
            queue_str = self.old_queue_str

        if not currently_playing_str:
            currently_playing_str = self.old_currently_playing_str

        page_count = math.ceil(len(self) / 10)
        if page_count == 0:
            page_count = 1

        self.old_queue_str = queue_str
        self.old_currently_playing_str = currently_playing_str
        self.old_page_count = page_count

        total_duration = sum([s.duration for s in self.queue])
        if current_song:
            total_duration += current_song.duration

        total_duration_formatted = format_time.ms(total_duration, accuracy=4)
        queue_str += f'\n\nSongs in queue: **{len(self)}**\nPlaylist duration: **{total_duration_formatted}**\nLoop: **{self.loop}**'

        if self.music_menu:
            new_embed = self.music_menu.embeds[0]
            new_embed.set_field_at(0, name='Currently Playing:', value=currently_playing_str, inline=False)
            new_embed.set_field_at(1, name='Queue:', value=queue_str, inline=False)
            new_embed.set_footer(text=f'Page {page}/{page_count}')
            await self.music_menu.edit(embed=new_embed)

    async def process_song(self, query, requester):
        is_url = query.startswith('https://')
        is_playlist = is_url and '&list=' in query

        if is_url:
            songs_data = await self.wavelink.get_tracks(f'{query}', retry_on_failure=True)
            if not songs_data:
                return f"Invalid url: {query}"

            if is_playlist:
                return await self.add(songs_data.tracks, requester)

            song = songs_data[0]
        else:
            songs_data = await self.wavelink.get_tracks(f'ytsearch:{query}', retry_on_failure=True)

            if not songs_data:
                return f"Couldn't find anything by: {query}"

            song = songs_data[0]

        await self.add(song, requester)

    def __len__(self):
        return len(self.queue)

    async def add(self, song, requester):
        player = self.wavelink.get_player(self.guild.id)

        if type(song) == list:
            song_list = song
            song = song_list[0]
        else:
            song_list = [song]

        song.info['requester'] = requester

        if self.current_song is None:
            self.current_song = song
            await self.update_music_menu(to_update='currently playing')
            await player.play(song)

        for song in song_list:
            song.info['requester'] = requester
            self.queue.append(song)

        return await self.update_music_menu(to_update='queue')

    async def next(self):
        previous_song = self.current_song
        self.current_song = None
        if len(self.queue) == 0:
            await self.update_music_menu()
            return None

        if self.loop:
            self.queue.append(previous_song)

        if len(self.queue) == 1:
            del self.queue[0]
            return await self.update_music_menu()

        next_song = self.queue.pop(0)

        self.current_song = next_song
        await self.update_music_menu()

        player = self.wavelink.get_player(self.guild.id)
        await player.play(next_song)

    async def shuffle(self):
        random.shuffle(self.queue)
        await self.update_music_menu(to_update='queue')

    async def clear(self):
        self.current_song = None
        self.queue.clear()
        await self.update_music_menu()

    async def clear_queue(self):
        self.queue.clear()
        await self.update_music_menu()


class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot

    @wavelink.WavelinkMixin.listener()
    async def on_track_end(self, node, payload):
        player = payload.player
        player_guild_id = player.guild_id
        playlist = self.bot.playlists[player_guild_id]

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
        player = playlist.wavelink.get_player(ctx.guild.id)
        await player.set_volume(new_volume)

        return await embed_maker.message(ctx, f'Volume has been changed to {new_volume}%', colour='green')

    @commands.command(help='Get the bot in a voice channel', usage='join', examples=['join'], clearance='User', cls=command.Command)
    async def join(self, ctx):
        if not ctx.author.voice:
            return await embed_maker.message(ctx, 'You need to be in a voice channel for me to join', colour='red'), 1

        voice_channel = ctx.author.voice.channel
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

        try:
            await player.connect(voice_channel.id)

            db.timers.delete_many({'guild_id': ctx.guild.id, 'event': 'playlist_clear'})

            return await embed_maker.message(ctx, f'Joined channel: **{voice_channel.name}**', colour='green', timestamp=None), 0
        except:
            return await embed_maker.message(ctx, 'Unable to connect to voice channel', colour='red', timestamp=None), 1

    @commands.command(help='Make the bot leave the voice channel', usage='leave', examples=['leave'], clearance='User', cls=command.Command)
    async def leave(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

        await player.stop()
        await player.disconnect()

        if len(playlist) > 5:
            clear_timer = db.timers.find_one({'guild_id': ctx.guild.id, 'event': 'playlist_clear'})
            if not clear_timer:
                utils_cog = self.bot.get_cog('Utils')
                expires = round(time.time()) + 300
                await utils_cog.create_timer(guild_id=ctx.guild.id, expires=expires, event='playlist_clear', extras={})

        elif len(playlist) >= 1:
            await player.destroy()
            await playlist.clear()

        return await ctx.message.add_reaction('👍')

    @commands.Cog.listener()
    async def on_playlist_clear_timer_over(self, timer):
        guild_id = timer['guild_id']
        playlist = self.bot.playlists[guild_id]
        player = playlist.wavelink.get_player(guild_id)
        await player.destroy()

        await playlist.clear()

    @commands.command(help='play a song from youtube', usage='play [song]', clearance='User', cls=command.Command,
                      examples=['play jack stauber buttercup', 'play https://www.youtube.com/watch?v=eYDI8b5Nn5s', 'play https://youtube.be/eYDI8b5Nn5s'])
    async def play(self, ctx, *, song_request=None):
        if song_request is None:
            return await embed_maker.command_error(ctx)

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

        if not player.is_connected:
            _, error = await ctx.invoke(self.join)
            if error:
                return

        return await playlist.process_song(song_request, ctx.author.id)

    @commands.command(help='pause the bot', usage='pause', clearance='User', examples=['pause'], cls=command.Command)
    async def pause(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

        if player.is_paused:
            return await embed_maker.message(ctx, 'Bot is already paused', colour='red')

        await player.set_pause(True)
        return await ctx.message.add_reaction('👍')

    @commands.command(help='unpause the bot', usage='unpause', clearance='User', examples=['unpause'], cls=command.Command)
    async def unpause(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

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
        player = playlist.wavelink.get_player(ctx.guild.id)

        await player.stop()

        return await ctx.message.add_reaction('👍')

    @commands.command(help="loop the playlist", usage='loop', examples=['loop'], clearance='User', cls=command.Command)
    async def loop(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        playlist.loop = True

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
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        await playlist.clear_queue()

        return await ctx.message.add_reaction('👍')

    async def check_voice(self, ctx):
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink.get_player(ctx.guild.id)

        if not player and not player.is_connected:
            return await embed_maker.message(ctx, "I'm not connected to any voice channel in this server", colour='red')

        if not ctx.author.voice.channel or ctx.author.voice.channel.id != player.channel_id:
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
        except:
            pass

        menu_embed = discord.Embed(colour=EMBED_COLOUR)
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


def setup(bot):
    bot.add_cog(Music(bot))
