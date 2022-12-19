from dataclasses import dataclass

from discord.ext.commands import Context as Dctx

from pipo.command import Command
from pipo.groovy import Groovy


@dataclass
class SkipList(Command):
    bot: Groovy
    ctx: Dctx

    async def execute(self) -> None:
        await self.bot.skip(self.ctx, skip_list=True)
