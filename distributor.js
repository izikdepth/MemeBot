const {
  getOrCreateAssociatedTokenAccount,
  createTransferInstruction,
} = require("@solana/spl-token");
const {
  Connection,
  Keypair,
  PublicKey,
  sendAndConfirmTransaction,
  Transaction,
  clusterApiUrl,
} = require("@solana/web3.js");

const cron = require("node-cron");

const sqlite3 = require("sqlite3").verbose();
const db = new sqlite3.Database("meme_bot.db");
const dotenv = require("dotenv").config(".env");
const bs58 = require("bs58");

const privateKey = process.env.PRIVATE_KEY; // replace with Solana wallet private key
//error handling
if (!privateKey) {
  console.error("Missing PRIVATE_KEY environment variable");
  return;
}
const decoded = bs58.decode(privateKey);

// Token Contract
const mintAddress = new PublicKey(process.env.MINT_ADDRESS);
// Connection
const connection = new Connection(clusterApiUrl("mainnet-beta"), "confirmed"); // replace with your node provider

const senderWallet = Keypair.fromSecretKey(Uint8Array.from(decoded));

async function sentTx() {
  // Token Decimals
  const tknDecimal = await decimal(mintAddress);
  db.serialize(() => {
    // Querying the DB
    db.all(
      "SELECT wallet_address, tokens, status FROM winners",
      [],
      async (err, rows) => {
        if (!err) {
          const query = rows;
          //
          for (items of query) {
            const wallet = await items.wallet_address;
            const amount = await items.tokens; //Amount entered
            const status = await items.status;

            // Check if value does not exist? skip
            if (wallet === null) continue;
            if (amount === 0) continue;
            if (status === 1) continue;

            // Receiver address[n]
            const receiver = new PublicKey(wallet);

            // Transfer Amount
            const transferAmount = (await amount) * Math.pow(10, tknDecimal);
            try {
              // initialise Transaction
              const transaction = new Transaction();
              // Get or create the associated token account Sender
              const senderAccount = await getOrCreateAssociatedTokenAccount(
                connection,
                senderWallet,
                mintAddress,
                senderWallet.publicKey
              );

              // Get or create the associated token account Receiver
              const receiverAccount = await getOrCreateAssociatedTokenAccount(
                connection,
                senderWallet,
                mintAddress,
                receiver
              );

              // Fill Tx
              transaction.add(
                createTransferInstruction(
                  senderAccount.address,
                  receiverAccount.address,
                  senderWallet.publicKey,
                  transferAmount
                )
              );

              // Sender tokens Amount
              const SenderTokenBalance = await getSplToken(mintAddress);
              const senderBal = SenderTokenBalance * Math.pow(10, tknDecimal);

              // Check if sent amount is greater than wallet Amount
              if (transferAmount > senderBal) return;

              // Set a delay before signing and sending the transaction
              const delayInSeconds = 10; //Delay of 10 seconds
              const delayInMilliseconds = delayInSeconds * 1000;
              await new Promise(resolve =>
                setTimeout(resolve, delayInMilliseconds)
              );

              // Set recent block
              let recentBlockHash = (await connection.getLatestBlockhash())
                .blockhash; //
              transaction.recentBlockhash = recentBlockHash;

              // Get recent block Height
              const recentBlockHeigh = await connection.getBlockHeight();
              transaction.recentBlockHeigh = recentBlockHeigh + 5;

              //Sign && sent TX
              const signAndSendTx = await sendAndConfirmTransaction(
                connection,
                transaction,
                [senderWallet]
              );
              console.log(`Tx hash: https://solscan.io/tx/${signAndSendTx}`);

              //update the DB
              const updateDB = `UPDATE winners SET status = 1
                                WHERE  wallet_address= ?;`;

              // change DB state
              if (signAndSendTx) {
                // change DBstatus to 1 => tokens sent to user
                db.run(updateDB, [wallet], err => {
                  if (!err) {
                    console.log(
                      `Status updated successfully for wallet: ${wallet}`
                    );
                  }
                });
              }

              // Get Tx signature
              const txState = await connection.getSignatureStatus(
                signAndSendTx
              );
              console.log(txState);
            } catch (err) {
              (async () => await retryLogic(sentTx))();
            }
          }
        } else {
          console.error(`Error querying table`, err.message);
        }
      }
    );
  });
}

// Call Function
sentTx();

// execute every 2hr
cron.schedule("*/2 * * * *", () => {
  sentTx();
});

// Call with token Account
async function getSplToken(mintAddress) {
  // getParsedTokenAccountsByOwner param
  const filter = { mint: mintAddress };
  // check if owner has spl token
  let accExist = await connection.getParsedTokenAccountsByOwner(
    senderWallet.publicKey,
    filter
  );

  // check if owner has enough spl to make tx
  accExist.value.forEach(accountInfo => {
    const uiAmount = accountInfo.account.data.parsed.info.tokenAmount.uiAmount;
    accExist = uiAmount;
  });

  return accExist;
}

// Get token decimal
async function decimal(mintAddress) {
  const accInfo = await connection.getParsedAccountInfo(mintAddress);
  const decimal = accInfo.value.data.parsed.info.decimals;
  return decimal;
}

// Retry Logic function
async function retryLogic(fn, retry = 10000, delay = 30000) {
  for (let attempt = 1; attempt <= retry; ++attempt) {
    try {
      const result = await fn();
      return result;
    } catch (err) {
      // if (err instanceof TokenAccountNotFoundError) continue; // Continue to the next attempt without waiting
      await new Promise(resolve => setTimeout(resolve, delay)); // Wait before retrying
    }
  }
  throw new Error(`failed after ${retry} attempts`);
}
