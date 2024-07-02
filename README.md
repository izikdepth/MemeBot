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

## TO RUN distributor.js

1. Download and install Node.js from the official [Website](https://nodejs.org/en)
2. Install npm packages `npm install @solana/spl-token @solana/web3.js node-cron sqlite3 dotenv bs58`
3. Run `node distributor.js`

### Notes:

- Ensure that the Python dependencies are correctly listed in `requirements.txt`.
- Ensure that your `distributor.js` script is set up to use the environment variables from the `.env` file.
- The above instructions assume that `distributor.js` is in the root of the project directory. Adjust the paths if necessary.
