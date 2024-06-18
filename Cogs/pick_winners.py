import os
import json
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
WINNERS_FILE = 'winners.json'

class PickWinners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.activity_counter = Counter()
        self.wallet_addresses = {}
        self.winners = self.load_winners()
        self.last_messages = {}
        self.channel_deletion_tasks = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if message.guild and message.guild.id != GUILD_ID:
            return

        self.activity_counter[message.author.id] += 1
        self.last_messages[message.author.id] = message

    @app_commands.command(name="submit_wallet", description="Submit your Solana wallet address")
    async def submit_wallet(self, interaction: discord.Interaction, wallet_address: str):
        await interaction.response.defer(ephemeral=True)

        if not any(interaction.user.id in day_winners for day_winners in self.winners.values()):
            await interaction.followup.send("You are not authorized to use this command.", ephemeral=True)
            return

        # ensure that commands are used in the channel created by the bot or in dm that was sent by the bot. 
        if isinstance(interaction.channel, discord.DMChannel) or (interaction.channel.name.startswith("wallet-")):
            self.wallet_addresses[interaction.user.id] = wallet_address
            admin = self.bot.get_user(ADMIN_ID)
            if admin:
                await admin.send(f"{interaction.user} has provided their Solana wallet address: ```{wallet_address}```")
            if interaction.channel.name.startswith("wallet-"):
                # cancel the task to delete the private channel created until after 24 hours or immediately after they submit their
                # addresses.
                if interaction.channel.id in self.channel_deletion_tasks:
                    self.channel_deletion_tasks[interaction.channel.id].cancel()
                    del self.channel_deletion_tasks[interaction.channel.id]
                # delete channel immediately after the winner submits their address.
                await interaction.channel.delete()
            await interaction.followup.send("Your wallet address has been submitted.", ephemeral=True)
        else:
            await interaction.followup.send("This command can only be used in the private wallet submission channel or in DMs.", ephemeral=True)

    @tasks.loop(hours=24)
    async def scoreboard_refresh(self):
        if not self.activity_counter:
            return

        top_members = self.activity_counter.most_common(10)
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        if current_date not in self.winners:
            self.winners[current_date] = []

        for member_id, _ in top_members:
            member = self.bot.get_user(member_id)
            if member:
                try:
                    msg = await member.send("Congratulations! You've made it to the 24-hour scoreboard. Please use the /submit_wallet command to provide your Solana wallet address within the next 24 hours.")
                    self.bot.loop.create_task(self.delete_dm_after_delay(member, msg, 24 * 3600))
                    self.winners[current_date].append(member_id)  # add the member to the winners list for today.
                    if member_id in self.last_messages:
                        await self.last_messages[member_id].add_reaction("🐂")  # react to last message the winner sent.
                except discord.Forbidden:
                    # create a private chat if the dm of the winner is closed.
                    guild = self.bot.get_guild(GUILD_ID)
                    if guild:
                        channel = await self.create_private_channel(guild, member)
                        if channel:
                            await channel.send(f"Hi {member.mention}, please use the /submit_wallet command to provide your Solana wallet address within the next 24 hours.")
                            self.winners[current_date].append(member_id)  # Add the member to the winners list for today.
                            # schedule the channel to be deleted after 24 hours.
                            task = self.bot.loop.create_task(self.delete_channel_after_delay(channel, 24 * 3600))
                            self.channel_deletion_tasks[channel.id] = task
                            self.bot.loop.create_task(self.delete_channel_after_delay(channel, 24 * 3600))

        self.save_winners()  # save winners to file.
        self.activity_counter.clear()
        self.last_messages.clear()

    async def create_private_channel(self, guild, member):
        # create a private text channel for the bot and the user.
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
            pass  # message might have already been deleted

    def save_winners(self):
        with open(WINNERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.winners, f, ensure_ascii=False)

    def load_winners(self):
        if os.path.exists(WINNERS_FILE):
            with open(WINNERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    @scoreboard_refresh.before_loop
    async def before_scoreboard_refresh(self):
        await self.bot.wait_until_ready()

    # method to start scoreboard_refresh task
    def start_scoreboard_refresh(self):
        self.scoreboard_refresh.start()

async def setup(bot):
    await bot.add_cog(PickWinners(bot))
    # register the commands if they're not already registered.
    if not bot.tree.get_command('submit_wallet'):
        bot.tree.add_command(PickWinners.submit_wallet)
