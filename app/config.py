import os
from dotenv import load_dotenv

load_dotenv()

MERCHANT_WALLET: str = os.getenv("MERCHANT_WALLET", "0x0000000000000000000000000000000000000000")
SKIP_PAYMENT: bool = os.getenv("SKIP_PAYMENT", "false").lower() == "true"

USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402/facilitator"
NETWORK = "eip155:8453"
GRACE_WINDOW_HOURS = 2

# Path to the SQLite database file. Default lives at the project root.
# Overridable via env var; tests point this at a per-test temp file.
DB_PATH: str = os.getenv("DB_PATH", "./sudoku.db")
