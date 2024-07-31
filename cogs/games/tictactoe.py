from typing import List
from discord.ext import commands
import discord
from discord import app_commands
import aiosqlite
from datetime import datetime
import os

GUILD_ID = int(os.getenv("GUILD_ID"))
TTT_MAX_USER_POINTS = int(os.getenv("TTT_MAX_USER_POINTS"))
TTT_TOTAL_DISTRIBUTION_LIMIT = int(os.getenv("TTT_TOTAL_DISTRIBUTION_LIMIT"))
TTT_POINTS_PER_WIN = int(os.getenv("TTT_POINTS_PER_WIN"))
DB_FILE = "meme_bot.db"

player1 = None
player2 = None

class TicTacToeButton(discord.ui.Button['TicTacToe']):
    def __init__(self, x: int, y: int):
        super().__init__(style=discord.ButtonStyle.secondary, label='\u200b', row=y)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        global player1, player2
        assert self.view is not None
        view: TicTacToe = self.view
        state = view.board[self.y][self.x]
        if state in (view.X, view.O):
            return
        if view.current_player == view.X:
            if interaction.user != player1:
                await interaction.response.send_message("It's not your Turn!", ephemeral=True)
            else:
                self.style = discord.ButtonStyle.danger
                self.label = 'X'
                self.disabled = True
                view.board[self.y][self.x] = view.X
                view.current_player = view.O
                content = f"It is now {player2.mention}'s turn **O**"
        else:
            if interaction.user != player2:
                await interaction.response.send_message("It's not your Turn!", ephemeral=True)
            else:
                self.style = discord.ButtonStyle.success
                self.label = 'O'
                self.disabled = True
                view.board[self.y][self.x] = view.O
                view.current_player = view.X
                content = f"It is now {player1.mention}'s turn **X**"
        
        winner = view.check_board_winner()
        if winner is not None:
            if winner == view.X:
                content = f'{player1.mention} **X** won!'
                await self.view.handle_winner(player1.id)
            elif winner == view.O:
                content = f'{player2.mention} **O** won!'
                await self.view.handle_winner(player2.id)
            else:
                content = "It's a tie!"
            for child in view.children:
                child.disabled = True
            view.stop()
        await interaction.response.edit_message(content=content, view=view)

class TicTacToe(discord.ui.View):
    children: List[TicTacToeButton]
    X = -1
    O = 1
    Tie = 2

    def __init__(self, client: commands.Bot):
        super().__init__()
        self.client = client
        self.current_player = self.X
        self.board = [
            [0, 0, 0],
            [0, 0, 0],
            [0, 0, 0],
        ]

        for x in range(3):
            for y in range(3):
                self.add_item(TicTacToeButton(x, y))

    def check_board_winner(self):
        for across in self.board:
            value = sum(across)
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        for line in range(3):
            value = self.board[0][line] + self.board[1][line] + self.board[2][line]
            if value == 3:
                return self.O
            elif value == -3:
                return self.X

        diag = self.board[0][2] + self.board[1][1] + self.board[2][0]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X
        diag = self.board[0][0] + self.board[1][1] + self.board[2][2]
        if diag == 3:
            return self.O
        elif diag == -3:
            return self.X
        
        if all(i != 0 for row in self.board for i in row):
            return self.Tie
        return None


    async def handle_winner(self, winner_id: int):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')
        
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT points, wallet_address FROM users WHERE user_id=?", (winner_id,)) as cursor:
                result = await cursor.fetchone()
                current_points = result[0] if result else 0
                has_wallet_address = bool(result[1]) if result else False

            async with db.execute("SELECT total_points_distributed FROM daily_points WHERE date=?", (current_date,)) as cursor:
                daily_points = await cursor.fetchone()
                total_points_distributed_today = daily_points[0] if daily_points else 0

            if current_points < TTT_MAX_USER_POINTS and total_points_distributed_today + TTT_POINTS_PER_WIN <= TTT_TOTAL_DISTRIBUTION_LIMIT:
                new_points = min(TTT_MAX_USER_POINTS - current_points, TTT_POINTS_PER_WIN)
                await db.execute("INSERT OR IGNORE INTO users (user_id, points) VALUES (?, ?)", (winner_id, 0))
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (new_points, winner_id))
                await db.execute("INSERT OR IGNORE INTO winners (date, user_id, points_earned, tokens, status) VALUES (?, ?, ?, ?, FALSE) ON CONFLICT(date, user_id) DO UPDATE SET points_earned = points_earned + ?, tokens = tokens + ?", (current_date, winner_id, new_points, new_points, new_points, new_points))
                await db.execute("INSERT OR IGNORE INTO daily_points (date, total_points_distributed) VALUES (?, 0)", (current_date,))
                await db.execute("UPDATE daily_points SET total_points_distributed = total_points_distributed + ? WHERE date = ?", (new_points, current_date))
                await db.commit()

                if not has_wallet_address:
                    user = self.client.get_user(winner_id)
                    if user:
                        await user.send("Congratulations on winning! Please submit your wallet address to claim your points.")


class TictactoeCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("TicTacToe is online.")

    @app_commands.command(name="tictactoe", description="Play TicTacToe.")
    @app_commands.describe(enemy="Player to challenge.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id))
    async def tictactoe(self, interaction: discord.Interaction, enemy: discord.Member):
        global player1, player2
        player1 = interaction.user
        player2 = enemy
        await interaction.response.send_message(f"Tic Tac Toe: {interaction.user.mention} goes first **X**", view=TicTacToe(self.client))
        
    @app_commands.command(name="ttt_guide", description="Learn how to play TicTacToe.")
    async def ttt_guide(self, interaction: discord.Interaction):
        guide_message = (
            "**TicTacToe Game Guide**\n\n"
            "TicTacToe is a simple two-player game where each player takes turns marking a square in a 3x3 grid with their symbol (X or O). "
            "The goal is to be the first player to get three of their symbols in a row, column, or diagonal.\n\n"
            "Here's how to play with this bot:\n"
            "1. Start a game by using the `/tictactoe` command and mentioning another player.\n"
            "2. The game board will appear, and you can mark your move by selecting a number corresponding to the position on the grid.\n"
            "3. The game will continue until one player wins or the board is full.\n\n"
            "For a visual guide, watch this video: [How to Play TicTacToe](https://www.youtube.com/watch?v=3qzcAMShotQ)\n\n"
            "Enjoy the game and good luck!"
        )
        await interaction.response.send_message(guide_message)


async def setup(bot: commands.Bot):
    cog = TictactoeCog(bot)
    await bot.add_cog(cog)
    if not bot.tree.get_command('tictactoe'):
        bot.tree.add_command(cog.tictactoe)
    if not bot.tree.get_command('ttt_guide'):
        bot.tree.add_command(cog.ttt_guide)
