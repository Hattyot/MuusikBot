from discord.ext import commands


class Group(commands.Group):
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        self.examples = kwargs['examples']
        if 'clearance' in kwargs:
            self.clearance = kwargs['clearance']
        if 'dm_only' in kwargs:
            self.dm_only = kwargs['dm_only']
        if 'sub_commands' in kwargs:
            self.sub_commands = kwargs['sub_commands']


class Command(commands.Command):
    def __init__(self, func, **kwargs):
        super().__init__(func, **kwargs)
        self.examples = kwargs['examples']
        if 'clearance' in kwargs:
            self.clearance = kwargs['clearance']
        if 'dm_only' in kwargs:
            self.dm_only = kwargs['dm_only']