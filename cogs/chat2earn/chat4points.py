import os
import asyncio
import random
from collections import Counter
from datetime import datetime, time
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import aiosqlite


def check_env_vars():
    required_vars = [
        "GUILD_ID",
        "REMINDER_CHANNEL_ID",
        "MAX_DAILY_POINTS",
        "MAX_USER_POINTS",
        "TOTAL_DISTRIBUTION_LIMIT",
        "POINTS_PER_MESSAGE",     
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
    else:
        print("All required environment variables are set.")
        
        
load_dotenv()
check_env_vars()

GUILD_ID = int(os.getenv('GUILD_ID'))
DB_FILE = 'meme_bot.db'
REMINDER_CHANNEL_ID = int(os.getenv('REMINDER_CHANNEL_ID'))
REMINDER_TIMES = [time(hour=10, minute=0), time(hour=22, minute=0)]  # 10:00 AM and 10:00 PM UTC

MAX_DAILY_POINTS = int(os.getenv("MAX_DAILY_POINTS"))
MAX_USER_POINTS = int(os.getenv("MAX_USER_POINTS"))
TOTAL_DISTRIBUTION_LIMIT = int(os.getenv("TOTAL_DISTRIBUTION_LIMIT"))
POINTS_PER_MESSAGE = int(os.getenv("POINTS_PER_MESSAGE"))
DELAY_24_HOURS_IN_SECONDS = 24 * 3600

class PickWinners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.activity_counter = Counter()
        self.wallet_addresses = {}
        self.last_messages = {}
        self.channel_deletion_tasks = {}
        self.bot.loop.create_task(self.init_db())
        self.scoreboard_refresh.start() # pylint: disable=no-member
        self.remind_wallet_submission.start() # pylint: disable=no-member

    async def init_db(self):
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS users (
                                user_id INTEGER PRIMARY KEY,
                                points INTEGER DEFAULT 0,
                                wallet_address TEXT,
                                last_activity DATE)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS winners (
                                date TEXT,
                                user_id INTEGER,
                                wallet_address TEXT,
                                points_earned INTEGER DEFAULT 0,
                                tokens INTEGER DEFAULT 0,
                                status BOOLEAN DEFAULT FALSE,
                                PRIMARY KEY (date, user_id))''')
            await db.execute('''CREATE TABLE IF NOT EXISTS daily_points (
                                date TEXT PRIMARY KEY,
                                total_points_distributed INTEGER DEFAULT 0)''')

            async with db.execute("PRAGMA table_info(winners)") as cursor:
                columns = [column[1] for column in await cursor.fetchall()]
                if 'status' not in columns:
                    await db.execute("ALTER TABLE winners ADD COLUMN status BOOLEAN DEFAULT FALSE")
                if 'points_earned' not in columns:
                    await db.execute("ALTER TABLE winners ADD COLUMN points_earned INTEGER DEFAULT 0")
                if 'tokens' not in columns:
                    await db.execute("ALTER TABLE winners ADD COLUMN tokens INTEGER DEFAULT 0")

            await db.commit()

    async def get_total_points_distributed_today(self):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT total_points_distributed FROM daily_points WHERE date = ?", (current_date,)) as cursor:
                result = await cursor.fetchone()
                return result[0] if result else 0

    async def update_total_points_distributed_today(self, points):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR IGNORE INTO daily_points (date, total_points_distributed) VALUES (?, 0)", (current_date,))
            await db.execute("UPDATE daily_points SET total_points_distributed = total_points_distributed + ? WHERE date = ?", (points, current_date))
            await db.commit()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or (message.guild and message.guild.id != GUILD_ID):
            return

        user_id = message.author.id
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        total_points_distributed_today = await self.get_total_points_distributed_today()

        if total_points_distributed_today >= TOTAL_DISTRIBUTION_LIMIT:
            return

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT points FROM users WHERE user_id=?", (user_id,)) as cursor:
                result = await cursor.fetchone()

            current_points = result[0] if result else 0

            if result is None:
                await db.execute("INSERT INTO users (user_id, last_activity) VALUES (?, ?)", (user_id, datetime.utcnow().date()))

            if current_points < MAX_USER_POINTS and total_points_distributed_today + POINTS_PER_MESSAGE <= TOTAL_DISTRIBUTION_LIMIT:
                if random.randint(1, 3) == 1:  # 1 in 3 chance
                    self.activity_counter[user_id] += 1
                    await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (POINTS_PER_MESSAGE, user_id))
                    await db.execute("INSERT OR IGNORE INTO winners (date, user_id, points_earned) VALUES (?, ?, 0)", (current_date, user_id))
                    await db.execute("UPDATE winners SET points_earned = points_earned + ? WHERE date = ? AND user_id = ?", (POINTS_PER_MESSAGE, current_date, user_id))
                    self.last_messages[user_id] = message
                    await self.update_total_points_distributed_today(POINTS_PER_MESSAGE)
                    await message.add_reaction("⛏️")

            await db.commit()

    @app_commands.command(name="submit_wallet", description="Submit your Solana wallet address")
    async def submit_wallet(self, interaction: discord.Interaction, wallet_address: str):
        user_id = interaction.user.id

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                result = await cursor.fetchone()

            if not result:
                await interaction.response.send_message("You are not registered. Please register first.", ephemeral=True)
                return

            async with db.execute("SELECT user_id FROM users WHERE wallet_address = ?", (wallet_address,)) as cursor:
                wallet_check = await cursor.fetchone()

            if wallet_check:
                await interaction.response.send_message("This wallet address has already been submitted. Please use a different wallet address.", ephemeral=True)
                return

            await db.execute("UPDATE users SET wallet_address = ? WHERE user_id = ?", (wallet_address, user_id))
            await db.commit()

            await interaction.response.send_message("Your wallet address has been submitted.", ephemeral=True)


    @tasks.loop(hours=24)
    async def scoreboard_refresh(self):
        if not self.activity_counter:
            return

        current_date = datetime.utcnow().strftime('%Y-%m-%d')

        async with aiosqlite.connect(DB_FILE) as db:
            for user_id in self.activity_counter.keys():
                async with db.execute("SELECT points, wallet_address FROM users WHERE user_id=?", (user_id,)) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        user_points = result[0]
                        wallet_address = result[1]
                        if user_points >= MAX_USER_POINTS or not wallet_address:
                            continue

                        await db.execute("UPDATE users SET points = 0 WHERE user_id = ?", (user_id,))
                        await db.execute(
                            "INSERT INTO winners (date, user_id, points_earned, tokens, status) VALUES (?, ?, ?, ?, FALSE) "
                            "ON CONFLICT(date, user_id) DO UPDATE SET points_earned = points_earned + ?, tokens = tokens + ?",
                            (current_date, user_id, user_points, user_points, user_points, user_points)
                        )
                        await db.commit()
                        member = self.bot.get_user(user_id)
                        if member:
                            try:
                                await member.send(
                                    "Congratulations! You've earned points today. Your wallet address is already on file."
                                )
                            except discord.Forbidden:
                                guild = self.bot.get_guild(GUILD_ID)
                                if guild:
                                    channel = await self.create_private_channel(guild, member)
                                    if channel:
                                        await channel.send(
                                            f"Hi {member.mention}, you've earned points today. Your wallet address is already on file."
                                        )
                                        task = self.bot.loop.create_task(
                                            self.delete_channel_after_delay(channel, DELAY_24_HOURS_IN_SECONDS)
                                        )
                                        self.channel_deletion_tasks[channel.id] = task

        self.activity_counter.clear()
        self.last_messages.clear()


    async def create_private_channel(self, guild, member):
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        channel = await guild.create_text_channel(f'wallet-{member.id}', overwrites=overwrites)
        return channel

    async def delete_channel_after_delay(self, channel, delay):
        await asyncio.sleep(delay)
        if channel:
            await channel.delete()

    async def delete_dm_after_delay(self, _member, message, delay):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.HTTPException as httperror:
            print(f"An error occurred while deleting dm after delay {httperror}")

    @scoreboard_refresh.before_loop
    async def before_scoreboard_refresh(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=12)
    async def remind_wallet_submission(self):
        await self.bot.wait_until_ready()
        current_time = datetime.utcnow().time()
        if any(REMINDER_TIME == current_time.replace(second=0, microsecond=0) for REMINDER_TIME in REMINDER_TIMES):
            channel = self.bot.get_channel(REMINDER_CHANNEL_ID)
            if channel:
                async with aiosqlite.connect(DB_FILE) as db:
                    async with db.execute("SELECT user_id FROM users WHERE wallet_address IS NULL") as cursor:
                        users_without_wallet = await cursor.fetchall()
                        if users_without_wallet:
                            await channel.send("@everyone Please submit your Solana wallet address if you haven't already using the /submit_wallet command!")


    @remind_wallet_submission.before_loop
    async def before_remind_wallet_submission(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    cog = PickWinners(bot)
    await bot.add_cog(cog)
    if not bot.tree.get_command('submit_wallet'):
        bot.tree.add_command(cog.submit_wallet)
