"""Integer pricing. Must stay byte-for-byte equivalent to chaincode/remit/pricing.go.
Shared test vectors in testvectors/quote_vectors.json guard the equivalence."""
BPS = 10_000
SCALE = 1_000_000
MAX_SEND_MINOR = 1_000_000_000
MAX_BPS = 500


def compute_quote(ccy, send_minor, mid_micro, spread_bps, fee_flat, fee_bps, expires_at=0):
    if not ccy:
        raise ValueError("send currency required")
    if send_minor <= 0 or send_minor > MAX_SEND_MINOR:
        raise ValueError("send amount out of range")
    if mid_micro <= 0:
        raise ValueError("mid rate must be positive")
    if not (0 <= spread_bps <= MAX_BPS and 0 <= fee_bps <= MAX_BPS):
        raise ValueError("spread/fee bps out of range")
    if fee_flat < 0:
        raise ValueError("flat fee must be >= 0")
    fee = fee_flat + send_minor * fee_bps // BPS
    if fee >= send_minor:
        raise ValueError("fee exceeds amount")
    eff = mid_micro * (BPS - spread_bps) // BPS
    receive = (send_minor - fee) * eff // SCALE
    mid_receive = send_minor * mid_micro // SCALE
    if mid_receive <= 0 or receive <= 0:
        raise ValueError("amount too small")
    cost = (mid_receive - receive) * BPS // mid_receive
    return {
        "sendCurrency": ccy, "sendAmountMinor": send_minor, "midRateMicro": mid_micro,
        "spreadBps": spread_bps, "feeFlatMinor": fee_flat, "feeBps": fee_bps,
        "feeTotalMinor": fee, "effectiveRateMicro": eff, "receivePaise": receive,
        "costBps": cost, "expiresAtUnix": expires_at,
    }
