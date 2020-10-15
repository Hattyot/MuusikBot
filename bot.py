import discord
import os
import config
import traceback
import time
import math
import subprocess
from cogs.music import Playlist
from modules import database
from cogs.utils import get_user_clearance
from discord.ext import commands

db = database.Connection()


async def get_prefix(bot, message):
    return commands.when_mentioned_or(config.PREFIX)(bot, message)


class Muusik(commands.Bot):
    def __init__(self):
        self.playlists = {}
        super().__init__(command_prefix=get_prefix, case_insensitive=True, help_command=None)

        # start lavalink
        self.lavalink_process = subprocess.Popen(['java', '-jar', 'Lavalink.jar'])

        # wait for lavalink to start
        time.sleep(10)
        # Load Cogs
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                self.load_extension(f'cogs.{filename[:-3]}')
                print(f'{filename[:-3]} is now loaded')

    async def on_raw_reaction_add(self, payload):
        guild_id = payload.guild_id
        channel_id = payload.channel_id
        message_id = payload.message_id

        # check if message is music menu
        playlist = self.playlists[guild_id]
        music_menu = playlist.music_menu
        if not music_menu or music_menu.id != message_id:
            return

        guild = await self.fetch_guild(guild_id)
        user_id = payload.user_id
        member = await guild.fetch_member(user_id)

        emote = payload.emoji.name
        if payload.emoji.is_custom_emoji():
            emote = f'<:{payload.emoji.name}:{payload.emoji.id}>'

        user_clearance = get_user_clearance(member)
        if member.bot or 'User' not in user_clearance:
            return

        player = playlist.wavelink.get_player(guild_id)

        async def play_pause():
            await player.set_pause(not player.is_paused)

        async def skip():
            await player.stop()

        async def loop():
            playlist.loop = not playlist.loop
            await playlist.update_music_menu()

        async def shuffle():
            await playlist.shuffle()

        async def back_page():
            current_page = playlist.music_menu_page
            new_page = current_page - 1
            if new_page < 1:
                page_count = math.ceil(len(playlist) / 5)
                new_page = page_count

            await playlist.update_music_menu(page=new_page)

        async def forward_page():
            current_page = playlist.music_menu_page
            new_page = current_page + 1
            page_count = math.ceil(len(playlist) / 5)
            if new_page > page_count:
                new_page = 1

            await playlist.update_music_menu(page=new_page)

        emote_functions = {
            '⏯': play_pause,
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
        verbosity = 4
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
        if message.nonce != 10:
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

    async def process_commands(self, message):
        ctx = await self.get_context(message)
        if ctx.command is None:
            return

        user_clearance = get_user_clearance(ctx.author)

        if ctx.command.clearance not in user_clearance:
            return

        return await self.invoke(ctx)

    async def on_ready(self):
        bot_game = discord.Game(f'@me')
        await self.change_presence(activity=bot_game)

        print(f'{self.user} is ready')

        for guild in self.guilds:
            self.playlists[guild.id] = Playlist(self, guild)

            dj_data = db.dj.find_one({'guild_id': guild.id})
            if dj_data:
                music_menu_channel_id = dj_data['music_menu_channel_id']
                music_menu_message_id = dj_data['music_menu_message_id']

                channel = guild.get_channel(music_menu_channel_id)
                if channel:
                    music_menu = await channel.fetch_message(music_menu_message_id)
                    self.playlists[guild.id].music_menu = music_menu
                    await self.playlists[guild.id].update_music_menu()

                    db.timers.delete_many({'guild_id': guild.id, 'event': 'playlist_clear'})

        # run old timers
        utils_cog = self.get_cog('Utils')
        await utils_cog.run_old_timers()

    async def on_voice_state_update(self, member, before, after):
        voice_channel = before.channel
        playlist = self.playlists[member.guild.id]
        player = playlist.wavelink.get_player(member.guild.id)

        if not voice_channel and after.channel:
            if player.is_paused:
                await player.set_pause(False)

            return db.timers.delete_many({'guild_id': member.guild.id, 'event': 'playlist_clear'})

        if not voice_channel:
            return

        connected_members = len(voice_channel.members)

        if connected_members == 1:
            await player.set_pause(True)
            clear_timer = db.timers.find_one({'guild_id': member.guild.id, 'event': 'playlist_clear'})
            if not clear_timer:
                utils_cog = self.get_cog('Utils')
                expires = round(time.time()) + 120
                await utils_cog.create_timer(guild_id=member.guild.id, expires=expires, event='playlist_clear', extras={})

    async def close(self):
        self.lavalink_process.kill()
        await super().close()

    def run(self):
        super().run(config.BOT_TOKEN, reconnect=False)


def main():
    Muusik().run()


if __name__ == '__main__':
    main()
