# MEME BOT

A simple Discord bot that picks the 10 most active members of a server (guild) and distributes tokens to them.

## Usage

1. Clone the repository:
    ```sh
    git clone https://github.com/izikdepth/MemeBot.git
    ```

2. Navigate to the project directory:
    ```sh
    cd MemeBot
    ```

3. Install the required packages:
    ```sh
    pip install -r requirements.txt
    ```
    or
    ```sh
    pip3 install -r requirements.txt
    ```

4. Create a Discord bot:
    Go to the [Discord Developer Dashboard](https://discord.com/developers/applications), create a bot, and copy your bot token. Then go to Discord -> Settings -> Advanced and enable Developer Mode. Next, click on your profile and "Copy User ID", then right-click on the server and "Copy Server ID".

5. Create a `.env` file:
    Copy and paste the contents of the `.env.example` file into the `.env` file, and fill it with the Guild ID (Server ID), Admin ID, and Bot Token.

6. Start the bot:
    ```sh
    python main.py
    ```
    or
    ```sh
    python3 main.py
    ```
## HOW THE BOT WORKS
**ACTIVITY REWARDER**
The bot monitors every member's activity and rewards them. Every message or other server engagement gets rewarded with points. Those points will later be converted to crypto tokens and automatically distributed to the members' wallet addresses. After 24 hours, the bot DMs everybody with recorded activity and asks them for their wallet addresses. They can then use the /submit_wallet command to submit their wallet addresses, and those wallet addresses will receive tokens. No single wallet address can be used twice in the same day.

**RAYDIUM LISTENER**
It periodically checks the Raydium (v4) pool for new liquidity pools. When there's a new liquidity pool, it fetches the new token's (not wrapped SOL) address and sends the Dexscreener link of that token to a specified Discord channel.


