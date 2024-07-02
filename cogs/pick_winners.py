import os
import sqlite3
from collections import Counter
from datetime import datetime
import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
import asyncio

load_dotenv()
ADMIN_ID = int(os.getenv('ADMIN_ID'))
GUILD_ID = int(os.getenv('GUILD_ID'))
DB_FILE = 'meme_bot.db'

MAX_DAILY_POINTS = int(os.getenv("MAX_DAILY_POINTS"))
MAX_USER_POINTS = int(os.getenv("MAX_USER_POINTS"))
TOTAL_DISTRIBUTION_LIMIT = int(os.getenv("TOTAL_DISTRIBUTION_LIMIT"))
POINTS_PER_MESSAGE = 500
# 24 * 3600 calculates the number of seconds in 24 hours (24 hours * 3600 seconds/hour)
DELAY_24_HOURS_IN_SECONDS = 24 * 3600
# TODO: Set delay for testing purposes
DELAY_FOR_TESTING_IN_SECONDS = 30

class PickWinners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.activity_counter = Counter()
        self.wallet_addresses = {}
        self.last_messages = {}
        self.channel_deletion_tasks = {}
        self.scoreboard_refresh.start()
        self.init_db()

    def init_db(self):
        # Connect to the database
        self.conn = sqlite3.connect(DB_FILE)
        self.cursor = self.conn.cursor()
        
        # Create users table if it does not exist
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                               user_id INTEGER PRIMARY KEY,
                               points INTEGER DEFAULT 0,
                               tokens INTEGER DEFAULT 0,
                               wallet_address TEXT,
                               last_activity DATE)''')
        
        # Create winners table if it does not exist
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS winners (
                               date TEXT,
                               user_id INTEGER,
                               wallet_address TEXT,
                               points_earned INTEGER DEFAULT 0,
                               status BOOLEAN DEFAULT FALSE,
                               PRIMARY KEY (date, user_id))''')

        # Add new columns if they do not exist
        self.cursor.execute("PRAGMA table_info(winners)")
        columns = [column[1] for column in self.cursor.fetchall()]
        if 'status' not in columns:
            self.cursor.execute("ALTER TABLE winners ADD COLUMN status BOOLEAN DEFAULT FALSE")
        if 'points_earned' not in columns:
            self.cursor.execute("ALTER TABLE winners ADD COLUMN points_earned INTEGER DEFAULT 0")

        # Create daily_points table if it does not exist
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS daily_points (
                               date TEXT PRIMARY KEY,
                               total_points_distributed INTEGER DEFAULT 0)''')

        self.conn.commit()

    def get_total_points_distributed_today(self):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        self.cursor.execute("SELECT total_points_distributed FROM daily_points WHERE date = ?", (current_date,))
        result = self.cursor.fetchone()
        if result:
            return result[0]
        return 0

    def update_total_points_distributed_today(self, points):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        self.cursor.execute("INSERT OR IGNORE INTO daily_points (date, total_points_distributed) VALUES (?, 0)", (current_date,))
        self.cursor.execute("UPDATE daily_points SET total_points_distributed = total_points_distributed + ? WHERE date = ?", (points, current_date))
        self.conn.commit()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild and message.guild.id != GUILD_ID:
            return

        user_id = message.author.id
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        total_points_distributed_today = self.get_total_points_distributed_today()

        if total_points_distributed_today >= TOTAL_DISTRIBUTION_LIMIT:
            return

        self.cursor.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
        result = self.cursor.fetchone()

        if result:
            current_points = result[0]
        else:
            self.cursor.execute("INSERT INTO users (user_id, last_activity) VALUES (?, ?)", (user_id, datetime.utcnow().date()))
            current_points = 0

        if current_points < MAX_USER_POINTS and total_points_distributed_today + POINTS_PER_MESSAGE <= TOTAL_DISTRIBUTION_LIMIT:
            self.activity_counter[user_id] += 1
            self.cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (POINTS_PER_MESSAGE, user_id))
            self.cursor.execute("INSERT OR IGNORE INTO winners (date, user_id, points_earned) VALUES (?, ?, 0)", (current_date, user_id))
            self.cursor.execute("UPDATE winners SET points_earned = points_earned + ? WHERE date = ? AND user_id = ?", (POINTS_PER_MESSAGE, current_date, user_id))
            self.last_messages[user_id] = message
            self.update_total_points_distributed_today(POINTS_PER_MESSAGE)

        self.conn.commit()

    @app_commands.command(name="submit_wallet", description="Submit your Solana wallet address")
    async def submit_wallet(self, interaction: discord.Interaction, wallet_address: str):
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        current_date = datetime.utcnow().strftime('%Y-%m-%d')

        # Check if the user is in the winners list for the current date
        self.cursor.execute("SELECT user_id FROM winners WHERE date = ? AND user_id = ?", (current_date, user_id))
        result = self.cursor.fetchone()

        if not result:
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return

        # Check if the wallet address is already in the database for the current date
        self.cursor.execute("SELECT user_id FROM winners WHERE date = ? AND wallet_address = ?", (current_date, wallet_address))
        wallet_check = self.cursor.fetchone()

        if wallet_check:
            await interaction.followup.send("This wallet address has already been submitted for today. Please use a different wallet address.", ephemeral=True)
            return

        if isinstance(interaction.channel, discord.DMChannel) or (isinstance(interaction.channel, discord.TextChannel) and interaction.channel.name.startswith("wallet-")):
            self.wallet_addresses[user_id] = wallet_address
            self.cursor.execute("UPDATE users SET wallet_address = ? WHERE user_id = ?", (wallet_address, user_id))
            self.conn.commit()
            
            if isinstance(interaction.channel, discord.TextChannel) and interaction.channel.name.startswith("wallet-"):
                if interaction.channel.id in self.channel_deletion_tasks:
                    self.channel_deletion_tasks[interaction.channel.id].cancel()
                    del self.channel_deletion_tasks[interaction.channel.id]
                await interaction.channel.delete()

            self.cursor.execute("UPDATE winners SET wallet_address = ? WHERE date = ? AND user_id = ?", (wallet_address, current_date, user_id))
            self.conn.commit()
            
            await interaction.followup.send("Your wallet address has been submitted.", ephemeral=True)
        else:
            await interaction.followup.send("This command can only be used in the private wallet submission channel or in DMs.", ephemeral=True)

    # TODO: change seconds to hours=24 for testing
    @tasks.loop(seconds=30)
    async def scoreboard_refresh(self):
        if not self.activity_counter:
            return

        current_date = datetime.utcnow().strftime('%Y-%m-%d')

        for user_id in self.activity_counter.keys():
            self.cursor.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
            result = self.cursor.fetchone()
            if result:
                user_points = result[0]
                if user_points >= MAX_USER_POINTS:
                    continue
                self.cursor.execute("UPDATE users SET points = 0, tokens = tokens + ? WHERE user_id = ?", (user_points, user_id))
                self.cursor.execute("INSERT INTO winners (date, user_id, points_earned, status) VALUES (?, ?, ?, FALSE) ON CONFLICT(date, user_id) DO UPDATE SET points_earned = points_earned + ?", (current_date, user_id, user_points, user_points))
                self.conn.commit()
                member = self.bot.get_user(user_id)
                if member:
                    try:
                        msg = await member.send("Congratulations! You've earned points today. Please use the /submit_wallet command to provide your Solana wallet address if you haven't already.")
                        # TODO: change DELAY_FOR_TESTING_IN_SECONDS to DELAY_24_HOURS_IN_SECONDS after testing
                        self.bot.loop.create_task(self.delete_dm_after_delay(member, msg, DELAY_FOR_TESTING_IN_SECONDS))
                        if user_id in self.last_messages:
                            await self.last_messages[user_id].add_reaction("🚀")
                    except discord.Forbidden:
                        guild = self.bot.get_guild(GUILD_ID)
                        if guild:
                            channel = await self.create_private_channel(guild, member)
                            if channel:
                                await channel.send(f"Hi {member.mention}, please use the /submit_wallet command to provide your Solana wallet address if you haven't already.")
                                # TODO: change DELAY_FOR_TESTING_IN_SECONDS to DELAY_24_HOURS_IN_SECONDS after testing
                                task = self.bot.loop.create_task(self.delete_channel_after_delay(channel, DELAY_FOR_TESTING_IN_SECONDS))
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

    async def delete_dm_after_delay(self, member, message, delay):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.HTTPException:
            pass

    @scoreboard_refresh.before_loop
    async def before_scoreboard_refresh(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    cog = PickWinners(bot)
    await bot.add_cog(cog)
    if not bot.tree.get_command('submit_wallet'):
        bot.tree.add_command(cog.submit_wallet)
