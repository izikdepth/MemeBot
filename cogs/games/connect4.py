import asyncio
import os
from typing import Union
from itertools import groupby, chain
from datetime import datetime
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite

def check_env_vars():
    required_vars = [
        "GUILD_ID",
        "CONNECT4_MAX_USER_POINTS",
        "CONNECT4_TOTAL_DISTRIBUTION_LIMIT",
        "CONNECT4_POINTS_PER_WIN",  
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")
    else:
        print("All required environment variables are set.")
        
load_dotenv()
check_env_vars()


GUILD_ID = int(os.getenv("GUILD_ID"))
MAX_USER_POINTS = int(os.getenv("CONNECT4_MAX_USER_POINTS"))
TOTAL_DISTRIBUTION_LIMIT = int(os.getenv("CONNECT4_TOTAL_DISTRIBUTION_LIMIT"))
POINTS_PER_WIN = int(os.getenv("CONNECT4_POINTS_PER_WIN"))
DB_FILE = 'meme_bot.db'

class Board(list):
    __slots__ = frozenset({'width', 'height'})
    def __init__(self, width, height, player1_name=None, player2_name=None):
        self.width = width
        self.height = height
        for _ in range(width):
            self.append([0] * height)

    def __getitem__(self, pos: Union[int, tuple]):
        if isinstance(pos, int):
            return list(self)[pos]
        elif isinstance(pos, tuple):
            x, y = pos
            return list(self)[x][y]
        else:
            raise TypeError('pos must be an int or tuple')

    def __setitem__(self, pos: Union[int, tuple], new_value):
        x, y = self._xy(pos)
        if self[x, y] != 0:
            raise IndexError("there's already a move at that position")
        # basically self[x][y] = new_value
        # super().__getitem__(x).__setitem__(y, new_value)
        self[x][y] = new_value

    def _xy(self, pos):
        if isinstance(pos, tuple):
            return pos[0], pos[1]
        elif isinstance(pos, int):
            x = pos
            return x, self._y(x)
        else:
            raise TypeError('pos must be an int or tuple')

    def _y(self, x):
        """find the lowest empty row for column x"""
        # start from the bottom and work up
        for y in range(self.height-1, -1, -1):
            if self[x, y] == 0:
                return y
        raise ValueError('that column is full')

    def _pos_diagonals(self):
        """Get positive diagonals, going from bottom-left to top-right."""
        for di in ([(j, i - j) for j in range(self.width)] for i in range(self.width + self.height - 1)):
            yield [self[i, j] for i, j in di if i >= 0 and j >= 0 and i < self.width and j < self.height]

    def _neg_diagonals(self):
        """Get negative diagonals, going from top-left to bottom-right."""
        for di in ([(j, i - self.width + j + 1) for j in range(self.height)] for i in range(self.width + self.height - 1)):
            yield [self[i, j] for i, j in di if i >= 0 and j >= 0 and i < self.width and j < self.height]

    def _full(self):
        """is there a move in every position?"""
        for x in range(self.width):
            if self[x, 0] == 0:
                return False
        return True

class Connect4Game:
    __slots__ = frozenset({'board', 'turn_count', '_whomst_forfeited', 'names'})
    FORFEIT = -2
    TIE = -1
    NO_WINNER = 0
    PIECES = (
        '\N{medium white circle}'
        '\N{large red circle}'
        '\N{large blue circle}'
    )

    def __init__(self, player1_name=None, player2_name=None):
        if player1_name is not None and player2_name is not None:
            self.names = (player1_name, player2_name)
        else:
            self.names = ('Player 1', 'Player 2')
        self.board = Board(7, 6)
        self.turn_count = 0
        self._whomst_forfeited = 0

    def move(self, column):
        self.board[column] = self.whomst_turn()
        self.turn_count += 1

    def forfeit(self):
        """forfeit the game as the current player"""
        self._whomst_forfeited = self.whomst_turn_name()

    def _get_forfeit_status(self):
        if self._whomst_forfeited:
            status = '{} won ({} forfeited)\n'
            return status.format(
                self.other_player_name(),
                self.whomst_turn_name()
            )
        raise ValueError('nobody has forfeited')

    def __str__(self):
        win_status = self.whomst_won()
        status = self._get_status()
        instructions = ''
        if win_status == self.NO_WINNER:
            instructions = self._get_instructions()
        elif win_status == self.FORFEIT:
            status = self._get_forfeit_status()
        return (
            status
            + instructions
            + '\n'.join(self._format_row(y) for y in range(self.board.height))
        )

    def _get_status(self):
        win_status = self.whomst_won()
        if win_status == self.NO_WINNER:
            status = (self.whomst_turn_name() + "'s turn"
                + self.PIECES[self.whomst_turn()])
        elif win_status == self.TIE:
            status = "It's a tie!"
        elif win_status == self.FORFEIT:
            status = self._get_forfeit_status()
        else:
            status = self._get_player_name(win_status) + ' won!'
        return status + '\n'

    def _get_instructions(self):
        instructions = ''
        for i in range(1, self.board.width+1):
            instructions += str(i) + '\N{combining enclosing keycap}'
        return instructions + '\n'

    def _format_row(self, y):
        return ''.join(self[x, y] for x in range(self.board.width))

    def __getitem__(self, pos):
        x, y = pos
        return self.PIECES[self.board[x, y]]

    def whomst_won(self):
        """Get the winner on the current board.
        If there's no winner yet, return Connect4Game.NO_WINNER.
        If it's a tie, return Connect4Game.TIE"""
        lines = (
            self.board, # columns
            zip(*self.board), # rows (zip picks the nth item from each column)
            self.board._pos_diagonals(), # positive diagonals
            self.board._neg_diagonals(), # negative diagonals
        )
        if self._whomst_forfeited:
            return self.FORFEIT
        for line in chain(*lines):
            for player, group in groupby(line):
                if player != 0 and len(list(group)) >= 4:
                    return player
        if self.board._full():
            return self.TIE
        else:
            return self.NO_WINNER

    def other_player_name(self):
        self.turn_count += 1
        other_player_name = self.whomst_turn_name()
        self.turn_count -= 1
        return other_player_name

    def whomst_turn_name(self):
        return self._get_player_name(self.whomst_turn())

    def whomst_turn(self):
        return self.turn_count%2+1

    def _get_player_name(self, player_number):
        player_number -= 1 # these lists are 0-indexed but the players aren't
        return self.names[player_number]

class Connect4(commands.Cog):
    CANCEL_GAME_EMOJI = '🚫'
    DIGITS = [str(digit) + '\N{combining enclosing keycap}' for digit in range(1, 8)] + ['🚫']
    VALID_REACTIONS = [CANCEL_GAME_EMOJI] + DIGITS
    GAME_TIMEOUT_THRESHOLD = 600

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Connect 4 is online.")

    @app_commands.command(name="connect4", description="Play Connect 4.")
    @app_commands.describe(player2="Player to challenge.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: (i.user.id))
    async def connect4(self, interaction: discord.Interaction, player2: discord.Member):
        if interaction.guild.id != GUILD_ID:
            await interaction.response.send_message("This game cannot be played in this server.", ephemeral=True)
            return

        player1 = interaction.user
        game = Connect4Game(player1.mention, player2.mention)
        await interaction.response.send_message("Game Started!", ephemeral=True)
        message = await interaction.channel.send(str(game))
        for digit in self.DIGITS:
            await message.add_reaction(digit)

        def check(reaction, user):
            return (
                user == (player1, player2)[game.whomst_turn() - 1]
                and str(reaction) in self.VALID_REACTIONS
                and reaction.message.id == message.id
            )

        while game.whomst_won() == game.NO_WINNER:
            try:
                reaction, user = await self.bot.wait_for(
                    'reaction_add',
                    check=check,
                    timeout=self.GAME_TIMEOUT_THRESHOLD
                )
            except asyncio.TimeoutError:
                game.forfeit()
                await message.reply("> Game was ended due to running out of time!")
                break

            await asyncio.sleep(0.2)
            try:
                await message.remove_reaction(reaction, user)
            except discord.errors.Forbidden:
                pass

            if str(reaction) == self.CANCEL_GAME_EMOJI:
                game.forfeit()
                break

            try:
                game.move(self.DIGITS.index(str(reaction)))
            except ValueError:
                pass
            await message.edit(content=str(game))

        await self.end_game(game, message, interaction)

    async def end_game(self, game, message, interaction):
        await message.edit(content=str(game))
        await self.clear_reactions(message)
        winner = game.whomst_won()
        if winner > 0:
            winner_id = (interaction.user.id if winner == 1 else interaction.data['options'][0]['value'])
            await self.update_winner_points(winner_id, interaction)

    async def update_winner_points(self, winner_id, interaction):
        current_date = datetime.utcnow().strftime('%Y-%m-%d')

        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT points FROM users WHERE user_id=?", (winner_id,)) as cursor:
                result = await cursor.fetchone()
                current_points = result[0] if result else 0

            async with db.execute("SELECT total_points_distributed FROM daily_points WHERE date=?", (current_date,)) as cursor:
                daily_points = await cursor.fetchone()
                total_points_distributed_today = daily_points[0] if daily_points else 0

            if current_points < MAX_USER_POINTS and total_points_distributed_today + POINTS_PER_WIN <= TOTAL_DISTRIBUTION_LIMIT:
                new_points = min(MAX_USER_POINTS - current_points, POINTS_PER_WIN)
                await db.execute("UPDATE users SET points = points + ? WHERE user_id = ?", (new_points, winner_id))
                await db.execute("INSERT OR IGNORE INTO winners (date, user_id, points_earned, tokens, status) VALUES (?, ?, ?, ?, FALSE) ON CONFLICT(date, user_id) DO UPDATE SET points_earned = points_earned + ?, tokens = tokens + ?", (current_date, winner_id, new_points, new_points, new_points, new_points))
                await db.execute("INSERT OR IGNORE INTO daily_points (date, total_points_distributed) VALUES (?, 0)", (current_date,))
                await db.execute("UPDATE daily_points SET total_points_distributed = total_points_distributed + ? WHERE date = ?", (new_points, current_date))
                await db.commit()
                await interaction.followup.send(f"Congratulations! You've been awarded {new_points} points.", ephemeral=True)
            else:
                await interaction.followup.send("The daily points limit has been reached or you've reached the maximum points.", ephemeral=True)

    @staticmethod
    async def clear_reactions(message):
        try:
            await message.clear_reactions()
        except discord.HTTPException:
            pass

    @app_commands.command(name="connect4_guide", description="Learn how to play Connect 4.")
    async def connect4_guide(self, interaction: discord.Interaction):
        guide_message = (
            "**Connect 4 Game Guide**\n\n"
            "Connect 4 is a two-player connection game in which the players take turns dropping colored discs from the top into a "
            "seven-column, six-row vertically suspended grid. The pieces fall straight down, occupying the lowest available space within the column. "
            "The objective of the game is to be the first to form a horizontal, vertical, or diagonal line of four of one's own discs.\n\n"
            "Here's how to play with this bot:\n"
            "1. Start a game by using the `/connect4` command and tagging another player.\n"
            "2. React to the game board message with a number (1-7) to drop your piece in that column.\n"
            "3. The game will continue until one player forms a line of four pieces or the board is full.\n"
            "4. If the game is not completed in time, it will end automatically.\n\n"
            "For a video guide, watch this : [How to Play Connect 4](https://www.youtube.com/watch?v=LK9PCdPwV-k)\n\n"
            "Enjoy the game and good luck!"
        )
        await interaction.response.send_message(guide_message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    cog = Connect4(bot)
    await bot.add_cog(cog)
    if not bot.tree.get_command('connect4'):
        bot.tree.add_command(cog.connect4)
    if not bot.tree.get_command('connect4_guide'):
        bot.tree.add_command(cog.connect4_guide)