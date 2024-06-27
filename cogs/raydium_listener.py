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

class RaydiumListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot 
        self.channel_id = os.getenv("DISCORD_CHANNEL_ID") # discord channel that receives the updates/new tokens
        self.wallet_address = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8" # raydium v4 address
        self.seen_signatures = set()
        self.solana_client = Client("https://api.mainnet-beta.solana.com") # api
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
        uri = "wss://api.mainnet-beta.solana.com"
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
            first_resp = await websocket.recv()
            response_dict = json.loads(first_resp)
            if 'result' in response_dict:
                print("Subscription successful. Subscription ID: ", response_dict['result'])
            
            async for response in websocket:
                response_dict = json.loads(response)
                if response_dict['params']['result']['value']['err'] is None:
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
