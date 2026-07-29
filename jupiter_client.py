"""
Thin wrapper around Jupiter's quote/swap API. Used both for real swaps
(PAPER_MODE=False) and to price paper trades against real live quotes
(PAPER_MODE=True), so simulated fills are realistic (real slippage,
real liquidity depth).
"""

import requests
import config


class JupiterClient:
    def __init__(self):
        self.quote_url = config.JUPITER_QUOTE_API
        self.swap_url = config.JUPITER_SWAP_API

    def get_quote(self, input_mint: str, output_mint: str, amount_lamports: int, slippage_bps: int = 100):
        params = {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "amount": amount_lamports,
            "slippageBps": slippage_bps,
        }
        resp = requests.get(self.quote_url, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_price_usd(self, mint: str) -> float:
        """Derive a rough USD price for `mint` by quoting a small SOL amount
        against it, then converting via SOL/USD. For production accuracy,
        consider Jupiter's dedicated price API or a price oracle instead."""
        quote = self.get_quote(config.BASE_MINT, mint, amount_lamports=1_000_000)  # 0.001 SOL
        out_amount = int(quote["outAmount"])
        in_amount = int(quote["inAmount"])
        sol_price_usd = self._get_sol_price_usd()
        sol_spent = in_amount / 1e9
        tokens_received = out_amount  # decimals vary per token — caller must adjust
        usd_spent = sol_spent * sol_price_usd
        return usd_spent, tokens_received

    def _get_sol_price_usd(self) -> float:
        # Simple public price feed for SOL/USD
        resp = requests.get(
            "https://price.jup.ag/v6/price", params={"ids": "SOL"}, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data["data"]["SOL"]["price"])

    def build_swap_transaction(self, quote: dict, user_pubkey: str):
        """Only used when PAPER_MODE = False. Returns a serialized
        transaction for the caller to sign and send."""
        payload = {
            "quoteResponse": quote,
            "userPublicKey": user_pubkey,
            "wrapAndUnwrapSol": True,
        }
        resp = requests.post(self.swap_url, json=payload, timeout=15)
        resp.raise_for_status()
        return resp.json()
