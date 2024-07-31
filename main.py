from discord.ext import commands
import os
from dotenv import load_dotenv
import asyncio
from discord import Intents

def check_env_vars():
    required_vars = [
        "DISCORD_BOT"     
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
    else:
        print("All required environment variables are set.")
        
load_dotenv()
check_env_vars()

intents = Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix="/", intents=intents)

@bot.event
async def on_ready():
    print("Bot is ready!")
    await bot.tree.sync()

async def load_cogs():
    cogs_list = [
        "cogs.chat2earn.chat4points",
        # "cogs.blockchainscanner.raydium_listener",
        "cogs.dc_commands",
        "cogs.games.connect4",
        "cogs.games.tictactoe",
    ]
    
    for cog in cogs_list:
        try:
            await bot.load_extension(cog)
            print(f'Loaded {cog} successfully.')
        except ImportError:
            print(f'Failed to load {cog}: ImportError occurred.')
        except AttributeError:
            print(f'Failed to load {cog}: AttributeError occurred.')

async def main():
    async with bot:
        await load_cogs()
        token = os.getenv("DISCORD_BOT")
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
