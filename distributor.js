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
  TransactionExpiredBlockheightExceededError,
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
// const networkProvider = process.env.ALCHEMY_MAINNET; // replace with your node provider
// //error handling
// if (!networkProvider) {
//   console.error("Missing ALCHEMY_MAINNET environment variable");
//   return;
// }

// Token Contract
const mintAddress = new PublicKey(process.env.MINT_ADDRESS);
// Connection
const connection = new Connection(clusterApiUrl("mainnet-beta"));

const senderWallet = Keypair.fromSecretKey(Uint8Array.from(decoded));

async function sentTx() {
  // Token Decimals
  const tknDecimal = await decimal(mintAddress);

  // Get or create the associated token account Sender
  const senderAccount = await getOrCreateAssociatedTokenAccount(
    connection,
    senderWallet,
    mintAddress,
    senderWallet.publicKey
  );

  // Get current date in YYYY-MM-DD format
  const currentDate = getCurrentDateInGMTPlus1();

  db.serialize(() => {
    // Querying the DB
    db.all("SELECT * FROM winners", [], async (err, rows) => {
      if (!err) {
        const query = rows; // Queried data

        for (items of query) {
          const date = await String(items.date); // Date sent
          const amount = await items.tokens; //Amount entered
          const wallet = await items.wallet_address; //Wallet[n]
          const status = await items.status;

          // Check if value does not exist? skip
          if (wallet === null) continue;

          // Receiver address[n]
          const receiver = new PublicKey(wallet);

          // Transfer Amount
          const transferAmount = (await amount) * Math.pow(10, tknDecimal);

          // Get or create the associated token account Receiver
          const receiverAccount = await getOrCreateAssociatedTokenAccount(
            connection,
            senderWallet,
            mintAddress,
            receiver
          );

          // initialise Transaction
          const transaction = new Transaction();

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
          if (transferAmount > senderBal) {
            console.log("INSUFFICIENT FUNDS");
            return;
          }

          // If date is not correct ? continue
          if (date === currentDate) {
            // Skip if status === 1. => tokens sent to address
            if (status === 1) {
              console.log(
                `Tokens Already sent to Wallet:${wallet} with the Status:${status}`
              );
              continue;
            }

            // Set recent block
            let recentBlockHash = (await connection.getLatestBlockhash())
              .blockhash; //
            transaction.recentBlockhash = recentBlockHash;

            // Get recent block Height
            const recentBlockHeigh = await connection.getBlockHeight();
            transaction.recentBlockHeigh = recentBlockHeigh + 5;

            console.log("ABOUT TO SEND TRANSACTION");
            //Sign && sent TX
            const signAndSendTx = await sendAndConfirmTransaction(
              connection,
              transaction,
              [senderWallet]
            );
            console.log(`TX HASH > https://solscan.io/tx/${signAndSendTx}`);

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
                } else console.error(err);
              });
            }

            // Get Tx signature
            const txState = await connection.getSignatureStatus(signAndSendTx);
            console.log(txState);

            // Will execute if an error is thrown
            await onTxErr(signAndSendTx);
          } else {
            console.log(`date is not === current Date`);
            continue;
          }
        }
      } else {
        console.error(`Error querying table`, err.message);
      }
    });
  });
  //// if i close the DB i get an error of misused DB functions
  // db.close();
}

// Call Function with retry logic
retryLogic(sentTx);

// execute every 24hrs 2mins
cron.schedule("0 0 * * *", () => {
  sentTx();
});

/// On error Function
async function onTxErr(signature) {
  const err = await new TransactionExpiredBlockheightExceededError(signature);
  return err;
}

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
async function retryLogic(fn, retry = 10, delay = 5000) {
  for (let attempt = 1; attempt < retry; ++attempt) {
    try {
      const result = await fn();
      return result;
    } catch (err) {
      if (attempt === retry) {
        throw new Error(`failed after ${retry} attempts: ${err.message}`);
      }
      console.log(`Attempt ${attempt} failed. Retrying in ${delay}ms...`);
      await new Promise(resolve => setTimeout(resolve, delay)); // Wait before retrying
    }
  }
}

const getCurrentDateInGMTPlus1 = () => {
  const currentDate = new Date();
  const offset = 1; // GMT+1
  currentDate.setHours(currentDate.getHours() + offset);
  const year = currentDate.getUTCFullYear();
  const month = String(currentDate.getUTCMonth() + 1).padStart(2, "0");
  const day = String(currentDate.getUTCDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

// // get current tx fee
// const fee = await connection.getRecentPrioritizationFees();

// // Function Get estimated tx fee
// async function estimatedTxFee(tx) {
//   const estimatedFee = await tx.getEstimatedFee(connection);
//   return estimatedFee;
// }
