import os
from dotenv import load_dotenv

load_dotenv()

MERCHANT_WALLET: str = os.getenv("MERCHANT_WALLET", "0x0000000000000000000000000000000000000000")
SKIP_PAYMENT: bool = os.getenv("SKIP_PAYMENT", "false").lower() == "true"
TESTNET: bool = os.getenv("TESTNET", "false").lower() == "true"

USDC_BASE = (
    "0x036CbD53842c5426634e7929541eC2318f3dCF7e" if TESTNET
    else "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
)
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
# x402 facilitator the resource server verifies/settles payments through.
# The CDP facilitator targets mainnet settlement and requires CDP API-key auth;
# the public x402.org facilitator is the canonical free testnet facilitator and
# supports Base Sepolia (eip155:84532) exact-scheme v2 without auth.
TESTNET_FACILITATOR_URL = "https://x402.org/facilitator"
FACILITATOR_URL = TESTNET_FACILITATOR_URL if TESTNET else CDP_FACILITATOR_URL
NETWORK = "eip155:84532" if TESTNET else "eip155:8453"
GRACE_WINDOW_HOURS = 2

# Path to the SQLite database file. Default lives at the project root.
# Overridable via env var; tests point this at a per-test temp file.
DB_PATH: str = os.getenv("DB_PATH", "./sudoku.db")
