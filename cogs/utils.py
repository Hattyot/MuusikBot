from discord.ext import commands
from modules import database
from datetime import datetime
from bson import ObjectId
from time import time
import config
import asyncio
import discord
import re

db = database.Connection()


async def get_member(ctx, bot, source):
    if source is None:
        return None

    if isinstance(source, int):
        source = str(source)

    member = None

    # check if source is member mention
    if ctx.message.mentions:
        member = ctx.message.mentions[0]

    # Check if source is user id
    elif source.isdigit() and len(source) > 10:
        member = ctx.guild.get_member(int(source))
        if member is None:
            try:
                return await ctx.guild.fetch_member(int(source))
            except:
                return 'Invalid user ID'

    # Check if source is member's name
    elif isinstance(source, str):
        if len(source) < 3:
            return 'User name input needs to be at least 3 characters long'

        # checks first for a direct name match
        members = list(filter(lambda m: m.name.lower() == source.lower() or m.display_name.lower() == source.lower(), ctx.guild.members))
        if not members:
            regex = re.compile(fr'({source.lower()})')
            # checks for regex match
            members = list(filter(lambda m: re.findall(regex, str(m).lower()) or re.findall(regex, m.display_name.lower()), ctx.guild.members))
            if len(members) > 10:
                return 'Too many username matches'

        if len(members) > 1:
            embed_colour = config.EMBED_COLOUR
            users_embed = discord.Embed(colour=embed_colour, timestamp=datetime.now())
            users_embed.set_author(name=f'Users')
            users_embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)

            description = 'Found multiple users, which one did you mean? `input digit of user`\n\n'
            for i, user in enumerate(members):
                description += f'`#{i + 1}` | {user.display_name}#{user.discriminator}'
                description += f' - **Username:** {user.name}#{user.discriminator}\n' if user.nick else '\n'

            users_embed.description = description

            await ctx.send(embed=users_embed)

            def user_check(m):
                return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

            try:
                user_message = await bot.wait_for('message', check=user_check, timeout=20)
            except asyncio.TimeoutError:
                return 'Timeout'

            index = user_message.content
            if index.isdigit() and len(members) >= int(index) - 1 >= 0:
                member = members[int(index) - 1]
            elif not index.isdigit():
                return 'Input is not a number'
            elif int(index) - 1 > len(members) or int(index) - 1 < 0:
                return 'Input number out of range'

        elif len(members) == 1:
            member = members[0]

    return member


def get_user_clearance(member):
    permissions = member.guild_permissions
    clearance = []

    if member.id in config.DEV_IDS:
        clearance.append('Dev')
    if permissions.administrator:
        clearance.append('Admin')
    if permissions.manage_messages:
        clearance.append('Mod')

    if not (set(config.NON_DJS) & set([r.id for r in member.roles])):
        clearance.append('User')

    return clearance


class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.loop = self.bot.loop
        self.event = asyncio.Event(loop=self.loop)

    async def run_old_timers(self):
        timers = db.timers.find({})
        if timers:
            print('running old timers')

        for timer in timers:
            asyncio.create_task(self.run_timer(timer))

    async def run_timer(self, timer):
        now = round(time())

        if timer['expires'] > now:
            await asyncio.sleep(timer['expires'] - now)

        await self.call_timer_event(timer)

    async def call_timer_event(self, timer):
        timer = db.timers.find_one({'_id': ObjectId(timer['_id'])})
        if not timer:
            return

        db.timers.delete_one({'_id': ObjectId(timer['_id'])})
        self.bot.dispatch(f'{timer["event"]}_timer_over', timer)

    async def create_timer(self, **kwargs):
        timer_dict = {
            'guild_id': kwargs['guild_id'],
            'expires': kwargs['expires'],
            'event': kwargs['event'],
            'extras': kwargs['extras']
        }

        db.timers.insert_one(timer_dict)
        asyncio.create_task(self.run_timer(timer_dict))


def setup(bot):
    bot.add_cog(Utils(bot))
