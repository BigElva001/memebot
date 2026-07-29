"""
Free alternative to X mention scanning. Uses DexScreener's public pair
data (buys/sells/volume) as a proxy for "the community is actively
interested" — no API key, no paid tier, no rate-limit wall.

It's a different kind of signal than X sentiment: instead of "people
are tweeting about this," it's "people are actually buying it, on
-chain, right now." Arguably more honest anyway — tweets are free,
swaps cost money.
"""

import config


def evaluate_activity(pair_data: dict) -> dict:
    """
    pair_data is one DexScreener pair object (see bot.get_pair_data).
    Returns: {"is_active": bool, "buys_h1": int, "sells_h1": int,
              "buy_sell_ratio": float, "volume_h1": float, "reason": str}
    """
    txns_h1 = (pair_data.get("txns") or {}).get("h1", {}) or {}
    buys = txns_h1.get("buys", 0) or 0
    sells = txns_h1.get("sells", 0) or 0
    volume_h1 = (pair_data.get("volume") or {}).get("h1", 0) or 0
    ratio = (buys / sells) if sells > 0 else (float("inf") if buys > 0 else 0)

    reasons = []
    if buys < config.MIN_BUYS_PER_HOUR:
        reasons.append(f"buys/hr too low ({buys} < {config.MIN_BUYS_PER_HOUR})")
    if ratio < config.MIN_BUY_SELL_RATIO:
        ratio_display = "inf" if ratio == float("inf") else f"{ratio:.2f}"
        reasons.append(
            f"buy/sell ratio too low ({ratio_display} < {config.MIN_BUY_SELL_RATIO})"
        )
    if volume_h1 < config.MIN_VOLUME_H1_USD:
        reasons.append(f"1hr volume too low (${volume_h1:,.0f} < ${config.MIN_VOLUME_H1_USD:,.0f})")

    is_active = len(reasons) == 0
    return {
        "is_active": is_active,
        "buys_h1": buys,
        "sells_h1": sells,
        "buy_sell_ratio": ratio,
        "volume_h1": volume_h1,
        "reason": "on-chain activity healthy" if is_active else "; ".join(reasons),
    }
