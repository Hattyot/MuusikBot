import discord
import config
from cogs.utils import get_user_clearance
from datetime import datetime
from discord.ext import commands
from modules import database, command, embed_maker

db = database.Connection()


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help='Get bot\'s latency', usage='ping', examples=['ping'], clearance='User', cls=command.Command)
    async def ping(self, ctx):
        message_created_at = ctx.message.created_at
        message = await ctx.send("Pong")
        ping = (datetime.utcnow() - message_created_at) * 1000
        await message.edit(content=f"\U0001f3d3 Pong   |   {int(ping.total_seconds())}ms")

    @commands.command(help='Get help smh', usage='help (command)', examples=['help', 'help ping'], clearance='User', cls=command.Command)
    async def help(self, ctx, _cmd=None, _sub_cmd=None):
        embed_colour = config.EMBED_COLOUR
        prefix = config.PREFIX
        all_commands = self.bot.commands
        help_object = {}

        user_clearance = get_user_clearance(ctx.author)
        for cmd in all_commands:
            if hasattr(cmd, 'dm_only'):
                continue

            if cmd.clearance not in user_clearance:
                continue

            if cmd.cog_name not in help_object:
                help_object[cmd.cog_name] = [cmd]
            else:
                help_object[cmd.cog_name].append(cmd)

        if _cmd is None:
            embed = discord.Embed(
                colour=embed_colour, timestamp=datetime.now(),
                description=f'**Prefix** : `{prefix}`\nFor additional info on a command, type `{prefix}help [command]`'
            )
            embed.set_author(name=f'Help - {user_clearance[0]}', icon_url=ctx.guild.icon_url)
            embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)

            # categories are listed in a list so they come out sorted instead of in a random order
            for cat in help_object.keys():
                if cat not in help_object:
                    continue
                # i need special access to be last
                if cat == 'Special Access':
                    continue

                embed.add_field(name=f'>{cat}', value=" \| ".join([f'`{c}`' for c in help_object[cat]]), inline=False)

            if 'Special Access' in help_object:
                embed.add_field(name=f'>Special Access', value=" \| ".join([f'`{c}`' for c in help_object['Special Access']]), inline=False)

            return await ctx.send(embed=embed)
        else:
            if self.bot.get_command(_cmd):
                cmd = self.bot.get_command(_cmd)
                if cmd.hidden:
                    return

                cog_name = cmd.cog_name

                if cmd.clearance != 'User' and cog_name == 'Leveling':
                    cog_name = 'Leveling - Staff'

                if cog_name not in help_object or cmd not in help_object[cog_name]:
                    return await embed_maker.message(ctx, f'{_cmd} is not a valid command')

                if _sub_cmd:
                    sub_cmd = cmd.get_command(_sub_cmd)
                    if sub_cmd is None:
                        return await embed_maker.message(ctx, f'{_sub_cmd} is not a valid sub command')

                examples = f' | {prefix}'.join(cmd.examples)
                cmd_help = f"""
                **Description:** {cmd.help}
                **Usage:** {prefix}{cmd.usage}
                **Examples:** {prefix}{examples}
                """

                if hasattr(cmd, 'sub_commands'):
                    sub_commands_str = '**Sub Commands:** ' + ' | '.join(s for s in cmd.sub_commands)
                    sub_commands_str += f'\n\nTo view more info about sub commands, type `{ctx.prefix}help {cmd.name} [sub command]`'
                    cmd_help += sub_commands_str

                embed = discord.Embed(colour=embed_colour, timestamp=datetime.now(), description=cmd_help)
                embed.set_author(name=f'Help - {cmd}', icon_url=ctx.guild.icon_url)
                embed.set_footer(text=f'{ctx.author}', icon_url=ctx.author.avatar_url)
                return await ctx.send(embed=embed)
            else:
                return await embed_maker.message(ctx, f'{_cmd} is not a valid command')


def setup(bot):
    bot.add_cog(Utility(bot))
