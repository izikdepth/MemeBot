import os
from dotenv import load_dotenv
from discord.ext import commands
from discord import Embed

load_dotenv()

class DiscordCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.contract_address = os.getenv("CONTRACT_ADDRESS")
        
    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot connected as {self.bot.user}')
       
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        keywords = ["ca", "contract", "contract address"]
        if any(keyword in message.content.lower() for keyword in keywords):
            embed = Embed(title="Contract Address", description=f"```\n{self.contract_address}\n```", color=0x00ff00)
            await message.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(DiscordCommands(bot))
