"""Simulated NPCI/UPI payout adapter (demo only). Replace with the real sandbox when access is granted."""
import difflib
import hashlib
import re

VPA_RE = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}$")


def name_match(declared: str, registered: str) -> int:
    a, b = declared.strip().lower(), registered.strip().lower()
    return int(round(difflib.SequenceMatcher(None, a, b).ratio() * 100))


def resolve_vpa(vpa: str, scenario: str = "happy") -> str | None:
    """Return the registered account holder name for a VPA (simulated).
    Returns None if format is invalid or cannot be resolved."""
    if not vpa or not VPA_RE.match(vpa):
        return None
    if scenario == "bad_beneficiary":
        return "Completely Different Person"
    # In simulated happy path, extract name from VPA handle or provide realistic match
    handle = vpa.split("@")[0].replace(".", " ").replace("_", " ").title()
    return handle if len(handle) >= 2 else "Verified Beneficiary"


def lookup_vpa(vpa: str, declared_name: str = "", scenario: str = "happy") -> dict:
    """Pre-send verification of beneficiary UPI ID."""
    if not vpa or not VPA_RE.match(vpa):
        return {
            "vpa": vpa,
            "status": "INVALID_FORMAT",
            "registeredName": None,
            "bank": None,
            "matchScore": 0,
            "verified": False,
            "message": "Invalid UPI VPA format. Expected name@bank."
        }
    
    registered = resolve_vpa(vpa, scenario=scenario)
    if not registered:
        return {
            "vpa": vpa,
            "status": "NOT_FOUND",
            "registeredName": None,
            "bank": None,
            "matchScore": 0,
            "verified": False,
            "message": "UPI VPA unresolvable with receiving bank."
        }
        
    bank = vpa.split("@")[1].upper()
    score = name_match(declared_name, registered) if declared_name else 100
    is_verified = score >= 70
    
    return {
        "vpa": vpa,
        "status": "VERIFIED" if is_verified else "NAME_MISMATCH",
        "registeredName": registered,
        "bank": bank,
        "matchScore": score,
        "verified": is_verified,
        "message": f"Verified: {registered} ({bank})" if is_verified else f"Name mismatch: Registered as '{registered}' ({score}% match)"
    }



def submit(remittance_id: str) -> str:
    return "PAY" + hashlib.sha256(remittance_id.encode()).hexdigest()[:12].upper()


def poll(remittance_id: str, scenario: str):
    if scenario == "payout_fail":
        return "FAILED", "BENEFICIARY_BANK_UNAVAILABLE"
    return "SUCCESS", "UPI" + hashlib.sha256(("upi" + remittance_id).encode()).hexdigest()[:12].upper()
