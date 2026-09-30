"""Notification system for remittance lifecycle events.

Simulates SMS/email notifications at each state change and provides
a beneficiary tracking endpoint. In production, replace the simulators
with actual messaging service integrations (Twilio, SendGrid, etc.).
"""
import time
from datetime import datetime, timezone

# Notification templates per status
TEMPLATES = {
    "CREATED": {
        "sender": "Your transfer {id} has been initiated for {corridor}.",
        "beneficiary": None,
    },
    "QUOTED": {
        "sender": "Your transfer {id} is locked at rate {rate}. Recipient gets {receive}.",
        "beneficiary": None,
    },
    "SCREENED": {
        "sender": "Your transfer {id} has passed compliance screening.",
        "beneficiary": None,
    },
    "HELD": {
        "sender": "Your transfer {id} is under review by our compliance team. We'll update you shortly.",
        "beneficiary": None,
    },
    "BLOCKED": {
        "sender": "Your transfer {id} has been blocked due to compliance policy. Contact support for details.",
        "beneficiary": None,
    },
    "VERIFIED": {
        "sender": "Recipient for transfer {id} has been verified.",
        "beneficiary": "You have a pending inbound transfer. Funds will arrive shortly.",
    },
    "BENEFICIARY_REJECTED": {
        "sender": "Transfer {id} rejected: recipient name does not match UPI records. A refund will be processed.",
        "beneficiary": None,
    },
    "FUNDED": {
        "sender": "Your transfer {id} has been funded. Payout is in progress.",
        "beneficiary": "An inbound transfer is being processed to your account.",
    },
    "PAYOUT_SUBMITTED": {
        "sender": "Payout for transfer {id} has been submitted to the recipient's bank.",
        "beneficiary": "Funds are being credited to your account.",
    },
    "SETTLED": {
        "sender": "Transfer {id} complete! {receive} has been credited to the recipient.",
        "beneficiary": "You've received {receive} via UPI. Reference: {upiRef}.",
    },
    "FAILED": {
        "sender": "Transfer {id} payout failed: {reason}. A refund will be processed.",
        "beneficiary": None,
    },
    "EXPIRED": {
        "sender": "Transfer {id} quote expired before funding. No money was moved.",
        "beneficiary": None,
    },
    "REFUNDED": {
        "sender": "Transfer {id} has been refunded. Reference: {refundRef}.",
        "beneficiary": None,
    },
}


class NotificationService:
    """Simulated notification service. Stores notifications in memory."""

    def __init__(self):
        self.notifications: list = []
        self._max = 1000

    def notify(self, remittance: dict, old_status: str = None):
        """Generate notifications for a state change."""
        status = remittance.get("status", "")
        template = TEMPLATES.get(status)
        if not template:
            return

        q = remittance.get("quote") or {}
        context = {
            "id": remittance.get("id", ""),
            "corridor": remittance.get("corridor", ""),
            "rate": f"{q.get('effectiveRateMicro', 0) / 1e6:.4f}" if q else "",
            "receive": f"₹{q.get('receivePaise', 0) / 100:,.2f}" if q else "",
            "upiRef": remittance.get("upiRef", ""),
            "refundRef": remittance.get("refundRef", ""),
            "reason": remittance.get("failReason", ""),
        }

        now = time.time()
        iso = datetime.fromtimestamp(now, timezone.utc).isoformat()

        if template["sender"]:
            self.notifications.append({
                "type": "sender",
                "channel": "sms",
                "remittanceId": remittance["id"],
                "status": status,
                "message": template["sender"].format(**context),
                "timestamp": now,
                "iso": iso,
                "read": False,
            })

        if template["beneficiary"]:
            self.notifications.append({
                "type": "beneficiary",
                "channel": "sms",
                "remittanceId": remittance["id"],
                "status": status,
                "message": template["beneficiary"].format(**context),
                "timestamp": now,
                "iso": iso,
                "read": False,
            })

        # Trim old notifications
        if len(self.notifications) > self._max:
            self.notifications = self.notifications[-self._max:]

    def get_for_remittance(self, rid: str) -> list:
        return [n for n in self.notifications if n["remittanceId"] == rid]

    def get_all(self, limit: int = 50) -> list:
        return list(reversed(self.notifications[-limit:]))

    def unread_count(self) -> int:
        return sum(1 for n in self.notifications if not n["read"])

    def mark_read(self, rid: str):
        for n in self.notifications:
            if n["remittanceId"] == rid:
                n["read"] = True


# Global instance
notifier = NotificationService()
