import discord
import ast
import config
import logging
import psutil
import copy
import time
import traceback
from discord.ext import commands
from config import DEV_IDS
from modules import database, command, embed_maker
from datetime import datetime
from cogs.utils import get_member

db = database.Connection()
logger = logging.getLogger(__name__)


def is_dev(ctx):
    return ctx.author.id in DEV_IDS


def insert_returns(body):
    if isinstance(body[-1], ast.Expr):
        body[-1] = ast.Return(body[-1].value)
        ast.fix_missing_locations(body[-1])

    if isinstance(body[-1], ast.If):
        insert_returns(body[-1].body)
        insert_returns(body[-1].orelse)

    if isinstance(body[-1], ast.With):
        insert_returns(body[-1].body)


class Dev(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(hidden=True, help='Time a command', usage='time_cmd [command]', examples=['time_cmd lb'],
                      clearance='Dev', cls=command.Command)
    async def time_cmd(self, ctx, *, cmd=None):
        if cmd is None:
            return await embed_maker.command_error(ctx)

        cmd_obj = self.bot.get_command(cmd)
        if cmd_obj is None:
            return await embed_maker.message(ctx, 'Invalid command', colour='red')

        msg = copy.copy(ctx.message)
        msg.content = ctx.prefix + cmd
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))

        start = time.perf_counter()
        try:
            await new_ctx.command.invoke(new_ctx)
        except commands.CommandError:
            end = time.perf_counter()
            success = False
            try:
                await ctx.send(f'```py\n{traceback.format_exc()}\n```')
            except discord.HTTPException:
                pass
        else:
            end = time.perf_counter()
            success = True

        colour='green' if success else 'red'
        await embed_maker.message(ctx, f'Success: {success} | Time: {(end - start) * 1000:.2f}ms', colour=colour)

    @commands.command(hidden=True, help='Run any command as another user', usage='sudo [user] [command]',
                      examples=['sudo hattyot lb'], clearance='Dev', cls=command.Command)
    async def sudo(self, ctx, user=None, *, cmd=None):
        if user is None or cmd is None:
            return await embed_maker.command_error(ctx)

        member = await get_member(ctx, self.bot, user)
        if member is None:
            return await embed_maker.message(ctx, 'Invalid user', colour='red')

        cmd_obj = self.bot.get_command(cmd)
        if cmd_obj is None:
            return await embed_maker.message(ctx, 'Invalid command', colour='red')

        msg = copy.copy(ctx.message)
        msg.channel = ctx.channel
        msg.author = member
        msg.content = config.PREFIX + cmd
        new_ctx = await self.bot.get_context(msg, cls=type(ctx))
        await self.bot.invoke(new_ctx)

    @commands.command(hidden=True, help='Reload an extension, so you dont have to restart the bot',
                      usage='reload_extension [ext]', examples=['reload_extension cogs.levels'],
                      clearance='Dev', cls=command.Command, aliases=['re'])
    @commands.check(is_dev)
    async def reload_extension(self, ctx, ext):
        if ext in self.bot.extensions.keys():
            self.bot.reload_extension(ext)
            return await embed_maker.message(ctx, f'{ext} has been reloaded', colour='green')
        else:
            return await embed_maker.message(ctx, 'That is not a valid extension', colour='red')

    @commands.command(hidden=True, help='Evaluate code', usage='eval [code]',
                      examples=['eval ctx.author.id'], clearance='Dev', cls=command.Command)
    @commands.check(is_dev)
    async def eval(self, ctx, *, cmd=None):
        if cmd is None:
            return await embed_maker.command_error(ctx)

        fn_name = "_eval_expr"
        cmd = cmd.strip("` ")

        cmd = "\n".join(f"    {i}" for i in cmd.splitlines())

        body = f"async def {fn_name}():\n{cmd}"

        parsed = ast.parse(body)
        body = parsed.body[0].body

        insert_returns(body)

        env = {
            'bot': ctx.bot,
            'discord': discord,
            'commands': commands,
            'ctx': ctx,
            '__import__': __import__,
            'db': db
        }
        exec(compile(parsed, filename="<ast>", mode="exec"), env)

        result = repr(await eval(f"{fn_name}()", env))
        # return done if result is empty, so it doesnt cause empty message error
        if result == '':
            result = 'Done'

        await ctx.send(result)

    @commands.command(hidden=True, help='Kill the bot', usage='kill_bot', examples=['kill_bot'], clearance='Dev', cls=command.Command)
    @commands.check(is_dev)
    async def kill_bot(self):
        await self.bot.close()

    @commands.command(hidden=True, help='monitors bot resource usage', usage='resource_usage', examples=['resource_usage'], clearance='Dev', cls=command.Command)
    @commands.check(is_dev)
    async def resource_usage(self, ctx):
        embed_colour = config.EMBED_COLOUR
        resource_overview = discord.Embed(colour=embed_colour, timestamp=datetime.now())
        resource_overview.set_footer(text=f'{ctx.author.name}#{ctx.author.discriminator}', icon_url=ctx.author.avatar_url)
        resource_overview.set_author(name='Resource Usage Overview', icon_url=ctx.guild.icon_url)
        resource_overview.add_field(name='**CPU Usage**', value=(str(psutil.cpu_percent()) + '%'), inline=False)
        resource_overview.add_field(name='**Memory Usage**', value=(str(psutil.virtual_memory().percent) + '%'), inline=False)
        await ctx.send(embed=resource_overview)


def setup(bot):
    bot.add_cog(Dev(bot))
