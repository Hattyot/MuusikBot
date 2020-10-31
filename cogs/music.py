import discord.utils
import math
import wavelink
import asyncio
import re
import config
import datetime
from discord.ext import commands
from modules import embed_maker, command, format_time, database
from modules.Playlist import Song

db = database.Connection()


class Music(commands.Cog, wavelink.WavelinkMixin):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_leave_vc_timer_over(self, timer):
        guild_id = timer['guild_id']
        playlist = self.bot.playlists[guild_id]
        player = playlist.wavelink_client.get_player(guild_id)

        playlist.current_song = None

        await player.stop()
        await player.disconnect()

    @wavelink.WavelinkMixin.listener()
    async def on_track_end(self, node, payload):
        player = payload.player
        playlist = self.bot.playlists[player.guild_id]

        playlist.current_song = None

        return await playlist.next()

    @commands.command(help='Jump to a position in the currently playing song', usage='seek [timestamp]', examples=['seek 1m 20s'], clearance='User', cls=command.Command)
    async def seek(self, ctx, *, new_position=None):
        if new_position is None:
            return await embed_maker.command_error(ctx)

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if not playlist.current_song:
            return await embed_maker.message(ctx, 'Nothing is playing currently', colour='red')

        if await self.check_voice(ctx):
            return

        correct_format = re.findall(r'((?:\d+h)? ?(?:\d+m)? ?(?:\d+s))', new_position)
        if not correct_format:
            return await embed_maker.message(ctx, 'Invalid timestamp format', colour='red')

        new_position = format_time.to_ms(timestamp=correct_format[0])
        duration = playlist.current_song.duration

        if new_position > duration:
            return await embed_maker.message(ctx, 'timestamp further than duration of song', colour='red')

        await player.seek(new_position)
        return await ctx.message.add_reaction('👍')

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

        await player.connect(voice_channel.id)
        return await embed_maker.message(ctx, f'Joined channel: **{voice_channel.name}**', colour='green', timestamp=None), 0

    @commands.command(help='Make the bot leave the voice channel', usage='leave', examples=['leave'], clearance='User', cls=command.Command)
    async def leave(self, ctx):
        if await self.check_voice(ctx):
            return

        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        playlist.current_song = None
        # playlist.old_progress_bar = ''
        # if playlist.progress_bar_task:
        #     playlist.progress_bar_task.cancel()

        await player.stop()
        await player.disconnect()

        return await ctx.message.add_reaction('👍')

    @commands.command(help='play a song from youtube', usage='play [song]', clearance='User', cls=command.Command,
                      examples=['play jack stauber buttercup', 'play https://www.youtube.com/watch?v=eYDI8b5Nn5s', 'play https://youtube.be/eYDI8b5Nn5s'])
    async def play(self, ctx, *, song_request=None):
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)

        if song_request is None:
            if playlist.current_song:
                await ctx.invoke(self.join)
                await player.play(playlist.current_song)
                return await playlist.update_music_menu()

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
            page = 1
            pages = {1: ''}
            if not playlists_data:
                pages[1] = f'Currently there are no playlists saved'
            else:
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

            embed = discord.Embed(title='Playlists', colour=config.EMBED_COLOUR, description=pages[page], timestamp=datetime.datetime.now())
            embed.set_footer(text=f'{ctx.author} - Page 1/{len(pages.keys())}', icon_url=ctx.author.avatar_url)

            playlist_msg = await ctx.channel.send(embed=embed)

            if len(pages.keys()) == 1:
                return

            reactions = ['◀', '▶']
            for reaction in reactions:
                await playlist_msg.add_reaction(reaction)

            def check(r, user):
                return user == ctx.author and str(r.emoji) in ['◀', '▶']

            async def reaction_menu(bot, message, menu_page):
                try:
                    r, user = await bot.wait_for('reaction_add', check=check, timeout=10)
                    page_count = len(pages.keys())
                    if str(r.emoji) == '▶':
                        menu_page += 1
                        if menu_page > page_count:
                            menu_page = 1
                    elif str(r.emoji) == '◀':
                        menu_page -= 1
                        if menu_page < 1:
                            menu_page = page_count

                    menu_embed = discord.Embed(title='Playlists', colour=config.EMBED_COLOUR, description=pages[menu_page], timestamp=datetime.datetime.now())
                    menu_embed.set_footer(text=f'{ctx.author} - Page {page}/{page_count}', icon_url=ctx.author.avatar_url)
                    await message.edit(embed=menu_embed)
                    await bot.http.remove_reaction(ctx.channel.id, message.id, str(r.emoji), ctx.author.id)
                    return await reaction_menu(bot, message, page)
                except asyncio.TimeoutError:
                    return 'Timeout'

            asyncio.create_task(reaction_menu(self.bot, playlist_msg, page))

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

        def check(m):
            return m.channel.id == ctx.channel.id and m.author.id == ctx.author.id

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

    @commands.command(help='Clear the playlist or only the queue', usage='clear (queue ?)', examples=['clear', 'clear q'], clearance='User', cls=command.Command)
    async def clear(self, ctx, queue=None):
        playlist = self.bot.playlists[ctx.guild.id]
        player = playlist.wavelink_client.get_player(ctx.guild.id)
        if queue:
            await playlist.clear_queue()
        else:
            await playlist.clear()
            await player.stop()

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
        if old_channel:
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
