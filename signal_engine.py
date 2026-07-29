"""
Combines the individual signals (social/on-chain activity, OG wallet
corroboration, liquidity, token age) into a single buy/no-buy decision
per token.

Deliberately conservative: ALL conditions must pass. A hot activity
signal alone is not enough - that's exactly the "you're the exit
liquidity" trap. Real wallet corroboration is required too.

Works with either signal source (X mentions or DexScreener on-chain
activity, see config.SIGNAL_SOURCE) - the caller (bot.py) computes
`social_active`/`social_reason` via whichever scanner is active and
passes the result in here unchanged.
"""

from dataclasses import dataclass

import config


@dataclass
class TokenSignal:
    symbol: str
    mint: str
    social_active: bool
    social_reason: str
    og_corroboration: int
    liquidity_usd: float
    token_age_min: float


def should_buy(signal: TokenSignal) -> tuple[bool, str]:
    reasons = []

    if not signal.social_active:
        reasons.append(signal.social_reason)
    if signal.og_corroboration < config.MIN_OG_CORROBORATION:
        reasons.append(
            f"insufficient OG wallet corroboration ({signal.og_corroboration} < {config.MIN_OG_CORROBORATION})"
        )
    if signal.liquidity_usd < config.MIN_LIQUIDITY_USD:
        reasons.append(
            f"liquidity too thin (${signal.liquidity_usd:,.0f} < ${config.MIN_LIQUIDITY_USD:,.0f}) - rug risk"
        )
    if signal.token_age_min < config.MIN_TOKEN_AGE_MIN:
        reasons.append(
            f"token too new ({signal.token_age_min:.0f}min < {config.MIN_TOKEN_AGE_MIN}min) - rug risk"
        )

    if reasons:
        return False, "; ".join(reasons)
    return True, "all signal thresholds met"
