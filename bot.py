import discord
import os
import config
import traceback
import math
import wavelink
import re
import subprocess
import time
from modules.Playlist import Playlist, Song
from modules import database, embed_maker
from cogs.utils import get_user_clearance
from discord.ext import commands

db = database.Connection()


async def get_prefix(bot, message):
    return commands.when_mentioned_or(config.PREFIX)(bot, message)


class Muusik(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=get_prefix, case_insensitive=True, help_command=None)

        self.in_container = os.environ.get('IN_DOCKER', False)
        if not self.in_container:
            self.lavalink_process = subprocess.Popen(['java', '-jar', 'Lavalink.jar'])
            # wait for lavalink to start
            time.sleep(20)  # TODO: probably should make this smarter by pining the url of lavalink rather than waiting

        # Load Cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                self.load_extension(f'cogs.{filename[:-3]}')
                print(f'{filename[:-3]} is now loaded')

        self.wavelink = wavelink.Client(bot=self)
        self.playlists = {}

    async def on_raw_reaction_add(self, payload):
        guild_id = payload.guild_id
        channel_id = payload.channel_id
        message_id = payload.message_id

        # check if message is music menu
        playlist = self.playlists[guild_id]
        music_menu = playlist.music_menu
        if not music_menu or music_menu.id != message_id:
            return

        guild = self.get_guild(guild_id)
        user_id = payload.user_id
        member = await guild.fetch_member(user_id)

        user_clearance = get_user_clearance(member)
        if member.bot or 'User' not in user_clearance:
            return

        emote = payload.emoji.name
        player = playlist.wavelink_client.get_player(guild_id)

        async def play_pause():
            if not player.is_connected and playlist.current_song:
                voice_state = guild._voice_states.get(member.id, None)
                if voice_state:
                    await player.connect(voice_state.channel.id)
                    await player.play(playlist.current_song)
                    return await playlist.update_music_menu()

            await player.set_pause(not player.is_paused)
            await playlist.update_music_menu()

        async def backwards():
            if playlist.history:
                if playlist.current_song:
                    playlist.queue = [playlist.current_song] + playlist.queue

                new_current = playlist.history.pop(-1)
                playlist.current_song = new_current
                playlist.update_dj_db()
                await playlist.update_music_menu()
                if player.is_connected:
                    await player.play(playlist.current_song)

        async def skip():
            if not player.is_connected and playlist.current_song:
                playlist.history.append(playlist.current_song)
                if len(playlist.history) > 20:
                    del playlist.history[0]

                playlist.current_song = None
                if playlist.queue:
                    playlist.current_song = playlist.queue[0]
                    playlist.update_dj_db()
                    del playlist.queue[0]
                return await playlist.update_music_menu()

            await player.stop()

        async def loop():
            playlist.loop = not playlist.loop
            await playlist.update_music_menu()

        async def shuffle():
            await playlist.shuffle()

        def page_count(playlist):
            pc = math.ceil(len(playlist) / 5)
            if pc < 1:
                pc = 1
            return pc

        async def back_page():
            current_page = playlist.music_menu_page
            new_page = current_page - 1
            pc = page_count(playlist)
            if new_page < 1 or new_page > pc:
                new_page = pc

            await playlist.update_music_menu(page=new_page)

        async def forward_page():
            current_page = playlist.music_menu_page
            new_page = current_page + 1
            pc = page_count(playlist)
            if new_page > pc:
                new_page = 1

            await playlist.update_music_menu(page=new_page)

        emote_functions = {
            '⏯': play_pause,
            '⏪': backwards,
            '⏩': skip,
            '🔄': loop,
            '🔀': shuffle,
            '◀': back_page,
            '▶': forward_page
        }

        await self.http.remove_reaction(channel_id, message_id, emote, user_id)

        if emote not in emote_functions:
            return

        func = emote_functions[emote]
        await func()

    async def on_message_edit(self, before, after):
        if before.content != after.content and after.content.startswith(config.PREFIX):
            return await self.process_commands(after)

    async def on_command_error(self, ctx, exception):
        trace = exception.__traceback__
        verbosity = 8
        lines = traceback.format_exception(type(exception), exception, trace, verbosity)
        traceback_text = ''.join(lines)

        if ctx.command.name == 'eval':
            return await ctx.send(f'```{exception}\n{traceback_text}```')

        print(traceback_text)
        print(exception)

        # send special message to user if bot lacks perms to send message in channel
        if hasattr(exception, 'original') and isinstance(exception.original, discord.errors.Forbidden):
            await ctx.author.send('It appears that I am not allowed to send messages in that channel')

        # send error message to certain channel in a guild if error happens during bot runtime
        if config.ERROR_SERVER in [g.id for g in self.guilds]:
            guild = self.get_guild(config.ERROR_SERVER)
        else:
            return print('Invalid error server id')

        if guild is not None:
            if config.ERROR_CHANNEL in [c.id for c in guild.channels]:
                channel = self.get_channel(config.ERROR_CHANNEL)
            else:
                return print('Invalid error channel id')

            embed_colour = config.EMBED_COLOUR
            embed = discord.Embed(colour=embed_colour, title=f'{ctx.command.name} - Command Error', description=f'```{exception}\n{traceback_text}```')
            embed.add_field(name='Message', value=ctx.message.content)
            embed.add_field(name='User', value=ctx.message.author)
            embed.add_field(name='Channel', value=f'{ctx.message.channel.name}')

            return await channel.send(embed=embed)

    async def on_message(self, message):
        music_menu = self.playlists[message.guild.id].music_menu
        if music_menu and music_menu.channel.id == message.channel.id and message.nonce != 10:
            await message.delete(delay=5)

        if message.author.bot:
            return

        # checks if message was sent in pms
        if message.guild is None:
            return

        if message.content.startswith(config.PREFIX):
            await self.process_commands(message)

        # checks if bot was mentioned, if it was invoke help command
        bot_mention = f'<@{self.user.id}>'
        bot_mention_nickname = f'<@!{self.user.id}>'

        if message.content == bot_mention or message.content == bot_mention_nickname:
            ctx = await self.get_context(message)
            utility_cog = self.get_cog('Utility')
            await utility_cog.help(ctx)

    async def on_guild_join(self, guild):
        self.playlists[guild.id] = Playlist(self, guild, self.wavelink)

    async def on_message_delete(self, message):
        music_menu = self.playlists[message.guild.id].music_menu
        if music_menu and music_menu.id == message.id:
            self.playlists[message.guild.id].music_menu = None

    async def process_commands(self, message):
        ctx = await self.get_context(message)
        if ctx.command is None:
            return

        user_clearance = get_user_clearance(ctx.author)

        if ctx.command.clearance not in user_clearance:
            return

        if not self.playlists[message.guild.id].music_menu and ctx.cog.qualified_name == 'Music' and ctx.command.name != 'music_menu':
            return await embed_maker.message(ctx, f'You can not use that command before setting up the music menu.'
                                                  f'\nYou can do that by typing `{config.PREFIX}music_menu`', nonce=10)

        return await self.invoke(ctx)

    async def on_ready(self):
        bot_game = discord.Game(f'@me')
        await self.change_presence(activity=bot_game)

        print(f'{self.user} is ready')
        db.timers.delete_many({'event': 'leave_vc'})

        # run old timers
        utils_cog = self.get_cog('Utils')
        await utils_cog.run_old_timers()

        for guild in self.guilds:
            self.playlists[guild.id] = Playlist(self, guild, self.wavelink)

            dj_data = db.dj.find_one({'guild_id': guild.id})
            if dj_data:
                music_menu_channel_id = dj_data['music_menu_channel_id']
                music_menu_message_id = dj_data['music_menu_message_id']

                channel = guild.get_channel(music_menu_channel_id)
                if channel:
                    try:
                        music_menu = await channel.fetch_message(music_menu_message_id)
                    except discord.HTTPException:
                        db.dj.update_one({'guild_id': guild.id}, {'$set': {'music_menu_channel_id': 0, 'music_menu_message_id': 0}})
                        self.playlists[guild.id].music_menu = None
                        return

                    playlist = self.playlists[guild.id]
                    playlist.music_menu = music_menu

                    # rebuild playlist
                    dj_data = db.dj.find_one({'guild_id': guild.id})
                    if 'playlist' in dj_data:
                        songs = dj_data['playlist']
                        for i, song in enumerate(songs):
                            song_id, requester, custom_title = song
                            track = Song(await self.wavelink.build_track(song_id), requester=requester)

                            regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
                            track.type = re.findall(regex, track.uri)[0].capitalize()
                            if custom_title:
                                track.custom_title = custom_title

                            if i == 0:
                                playlist.current_song = track
                                continue

                            playlist.queue.append(track)

                    await playlist.update_music_menu()

                    if 'history' in dj_data:
                        history_songs = dj_data['history']
                        for song in history_songs:
                            song_id, requester, custom_title = song
                            track = Song(await self.wavelink.build_track(song_id), requester=requester)
                            regex = r'https:\/\/(?:www)?.?([A-z]+)\.(?:com|tv)'
                            track.type = re.findall(regex, track.uri)[0].capitalize()
                            if custom_title:
                                track.custom_title = custom_title
                            playlist.history.append(track)

    async def on_voice_state_update(self, member, before, after):
        voice_channel = before.channel
        playlist = self.playlists[member.guild.id]
        player = playlist.wavelink_client.get_player(member.guild.id)

        # resume bot and playlist when someone joins back
        if not voice_channel and after.channel:
            if player.is_paused:
                await player.set_pause(False)

        if not voice_channel:
            return

        connected_members = len(voice_channel.members)

        # pause bot when last person leaves and start 2m timer to clear playlist
        if connected_members == 1:
            await player.set_pause(True)

    async def close(self):
        if not self.in_container:
            self.lavalink_process.kill()

        await super().close()

    def run(self):
        super().run(config.BOT_TOKEN, reconnect=False)


def main():
    Muusik().run()


if __name__ == '__main__':
    main()
