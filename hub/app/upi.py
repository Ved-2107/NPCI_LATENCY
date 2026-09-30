"""Simulated NPCI/UPI payout adapter (demo only). Replace with the real sandbox when access is granted."""
import difflib
import hashlib
import re

VPA_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


def name_match(declared: str, registered: str) -> int:
    a, b = declared.strip().lower(), registered.strip().lower()
    return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))


def resolve_vpa(vpa: str, scenario: str) -> str | None:
    """Return the registered account holder name for a VPA (simulated)."""
    if not VPA_RE.match(vpa):
        return None
    if scenario == "bad_beneficiary":
        return "Completely Different Person"
    return None  # caller falls back to declared name (match = 100)


def submit(remittance_id: str) -> str:
    return "PAY" + hashlib.sha256(remittance_id.encode()).hexdigest()[:12].upper()


def poll(remittance_id: str, scenario: str):
    if scenario == "payout_fail":
        return "FAILED", "BENEFICIARY_BANK_UNAVAILABLE"
    return "SUCCESS", "UPI" + hashlib.sha256(("upi" + remittance_id).encode()).hexdigest()[:12].upper()
