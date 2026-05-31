#!/usr/bin/env python3
"""One-time setup: create merchant and user wallets on Base Sepolia, fund with ETH."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from eth_account import Account

load_dotenv()

ENV_TESTNET = Path(".env.testnet")
FAUCET_NETWORK = "base-sepolia"
FAUCET_TOKEN = "eth"
MERCHANT_ACCOUNT_NAME = "sudoku-merchant"


async def main() -> None:
    for var in ("CDP_API_KEY_ID", "CDP_API_KEY_SECRET", "CDP_WALLET_SECRET"):
        if not os.environ.get(var):
            print(f"ERROR: {var} is not set. Export it before running this script.")
            sys.exit(1)

    if ENV_TESTNET.exists():
        answer = input(f"{ENV_TESTNET} already exists. Overwrite? [y/N]: ").strip().lower()
        if answer != "y":
            print("Aborted.")
            sys.exit(0)

    from cdp import CdpClient

    async with CdpClient() as cdp:
        print(f"Creating/fetching CDP account '{MERCHANT_ACCOUNT_NAME}'...")
        merchant = await cdp.evm.get_or_create_account(MERCHANT_ACCOUNT_NAME)
        print(f"  Merchant address: {merchant.address}")

        print("  Requesting testnet ETH for merchant...")
        try:
            tx = await cdp.evm.request_faucet(merchant.address, FAUCET_NETWORK, FAUCET_TOKEN)
            print(f"  ETH faucet tx: {tx}")
        except Exception as e:
            print(f"  WARNING: ETH faucet failed for merchant: {e}")

        print("Generating local user key pair...")
        user_account = Account.create()
        print(f"  User address: {user_account.address}")

        print("  Requesting testnet ETH for user...")
        try:
            tx = await cdp.evm.request_faucet(user_account.address, FAUCET_NETWORK, FAUCET_TOKEN)
            print(f"  ETH faucet tx: {tx}")
        except Exception as e:
            print(f"  WARNING: ETH faucet failed for user: {e}")

    ENV_TESTNET.write_text(
        f"MERCHANT_WALLET={merchant.address}\n"
        f"USER_WALLET_ADDRESS={user_account.address}\n"
        f"USER_PRIVATE_KEY=0x{user_account.key.hex()}\n"
    )
    print(f"\n.env.testnet written to {ENV_TESTNET.resolve()}")

    print("\n" + "=" * 60)
    print("NEXT STEP: Fund both wallets with USDC on Base Sepolia.")
    print("Go to: https://faucet.circle.com")
    print("Select network: Base Sepolia, token: USDC")
    print(f"  Merchant: {merchant.address}")
    print(f"  User:     {user_account.address}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
