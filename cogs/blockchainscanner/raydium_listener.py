import websockets
import json
from solana.rpc.api import Client
from solders.pubkey import Pubkey
from solders.signature import Signature
import pandas as pd
from tabulate import tabulate
from discord.ext import commands
from discord import Embed
import os
from dotenv import load_dotenv

load_dotenv()

RPC_URL = "http://86.109.8.241:8899/"
WS_URL = "ws://86.109.8.241:8900/"

class RaydiumListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 
        self.channel_id = os.getenv("DISCORD_CHANNEL_ID")
        self.wallet_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        self.seen_signatures = set()
        self.solana_client = Client(RPC_URL)
        self.bot.loop.create_task(self.run_listener())

    def getTokens(self, str_signature):
        signature = Signature.from_string(str_signature)
        transaction = self.solana_client.get_transaction(signature, encoding="jsonParsed",
                                                         max_supported_transaction_version=0).value
        instruction_list = transaction.transaction.transaction.message.instructions
        for instructions in instruction_list:
            if instructions.program_id == Pubkey.from_string(self.wallet_address):
                print("============NEW POOL DETECTED====================")
                Token0 = instructions.accounts[8]
                Token1 = instructions.accounts[9]
                if Token0 == "So11111111111111111111111111111111111111112":
                    return Token1
                data = {'Token_Index': ['Token0', 'Token1'],
                        'Account Public Key': [Token0, Token1]}
                df = pd.DataFrame(data)
                table = tabulate(df, headers='keys', tablefmt='fancy_grid')
                print(table)
                return Token0 

    async def send_discord_message(self, content):
        channel = self.bot.get_channel(int(self.channel_id))
        if channel is None:
            return
        
        embed = Embed(title="New Pool Detected", description=f"Dexscreener: {content}", color=0x00ff00)
        await channel.send(embed=embed)

    async def run_listener(self):
        await self.bot.wait_until_ready()
        uri = WS_URL
        async with websockets.connect(uri) as websocket:
            await websocket.send(json.dumps({
                "jsonrpc": "2.0",
                "id": 1,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [self.wallet_address]},
                    {"commitment": "finalized"}
                ]
            }))
            print("Subscription request sent.")
            
            async for response in websocket:
                response_dict = json.loads(response)
                print("Received message:", response_dict)  # Print received message for debugging
                if 'params' in response_dict and 'result' in response_dict['params'] and 'value' in response_dict['params']['result']:
                    signature = response_dict['params']['result']['value']['signature']
                    if signature not in self.seen_signatures:
                        self.seen_signatures.add(signature)
                        log_messages_set = set(response_dict['params']['result']['value']['logs'])
                        search = "initialize2"
                        if any(search in message for message in log_messages_set):
                            print(f"True, https://solscan.io/tx/{signature}")
                            token0 = self.getTokens(signature)
                            if token0:
                                link = f"https://dexscreener.com/solana/{token0}"
                                await self.send_discord_message(link)

async def setup(bot):
    await bot.add_cog(RaydiumListener(bot))
