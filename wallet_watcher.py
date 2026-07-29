"""
Watches a list of Solana wallets (config.OG_WALLETS) for new token buys,
via Solana RPC. Used to corroborate social signal with actual on-chain
"smart money" behavior — much harder to fake than tweet volume.
"""

import time
import requests
from collections import defaultdict

import config


class WalletWatcher:
    def __init__(self, rpc_url: str = None):
        self.rpc_url = rpc_url or config.SOLANA_RPC_URL
        # recent buys: {mint: [(wallet, timestamp), ...]}
        self._recent_buys = defaultdict(list)

    def _rpc(self, method: str, params: list):
        resp = requests.post(
            self.rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(data["error"])
        return data["result"]

    def get_recent_token_transfers(self, wallet: str, limit: int = 20):
        """Fetch recent signatures for a wallet, then parse transfers.
        This is a simplified version — for production use, a dedicated
        indexer (Helius, Triton, etc.) is far more reliable than raw RPC."""
        sigs = self._rpc(
            "getSignaturesForAddress", [wallet, {"limit": limit}]
        )
        transfers = []
        for sig_info in sigs:
            sig = sig_info["signature"]
            try:
                tx = self._rpc(
                    "getTransaction",
                    [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                )
            except Exception:
                continue
            if not tx:
                continue
            transfers.append((sig, tx.get("blockTime")))
        return transfers

    def poll(self, wallets: list = None):
        """
        Call this on a loop. Updates self._recent_buys with any new
        token acquisitions seen for watched wallets. Real parsing of
        SPL token transfer instructions is left as a hookable step —
        plug in Helius' enhanced transactions API here for reliability
        (https://docs.helius.dev) rather than parsing raw instructions.
        """
        wallets = wallets or config.OG_WALLETS
        if not wallets:
            return {}
        # Placeholder loop structure — wire in real parsing via Helius
        # or a similar indexer for production use.
        for wallet in wallets:
            try:
                self.get_recent_token_transfers(wallet)
            except Exception:
                continue
        return self._recent_buys

    def corroboration_for(self, mint: str) -> int:
        """How many distinct watched wallets bought `mint` within the
        configured corroboration window."""
        cutoff = time.time() - config.WALLET_CORROBORATION_WINDOW_MIN * 60
        recent = [w for w, ts in self._recent_buys.get(mint, []) if ts and ts >= cutoff]
        return len(set(recent))
