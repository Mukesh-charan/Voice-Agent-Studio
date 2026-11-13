"""
Voice Agent Studio - Guardrailing & Role-Based Access Control (RBAC) Module
Provides:
1. Multi-role access control (Owner, Manager, Receptionist, Viewer)
2. Sensitive information abstraction and PII masking for booked rooms
3. Conversational in-call privacy guardrail to prevent guest data leaks
4. Transcript PII redaction based on caller/member role
"""

import re
from typing import Dict, List, Optional, Tuple, Any

# =====================================================================
# 1. ROLES & PERMISSIONS
# =====================================================================

ROLE_OWNER = "owner"
ROLE_MANAGER = "manager"
ROLE_RECEPTIONIST = "receptionist"
ROLE_VIEWER = "viewer"

ROLES_LIST = [ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTIONIST, ROLE_VIEWER]

ROLE_RANKS = {
    ROLE_OWNER: 4,
    ROLE_MANAGER: 3,
    ROLE_RECEPTIONIST: 2,
    ROLE_VIEWER: 1,
}

PERMISSIONS = {
    ROLE_OWNER: {
        "can_delete_agent": True,
        "can_edit_settings": True,
        "can_manage_members": True,
        "can_manage_knowledge": True,
        "can_view_sensitive_data": True,
        "can_edit_bookings": True,
        "can_delete_bookings": True,
        "can_call": True,
    },
    ROLE_MANAGER: {
        "can_delete_agent": False,
        "can_edit_settings": False,
        "can_manage_members": False,
        "can_manage_knowledge": True,
        "can_view_sensitive_data": True,
        "can_edit_bookings": True,
        "can_delete_bookings": True,
        "can_call": True,
    },
    ROLE_RECEPTIONIST: {
        "can_delete_agent": False,
        "can_edit_settings": False,
        "can_manage_members": False,
        "can_manage_knowledge": False,
        "can_view_sensitive_data": False,  # ABSTRACTED / MASKED
        "can_edit_bookings": False,
        "can_delete_bookings": False,
        "can_call": True,
    },
    ROLE_VIEWER: {
        "can_delete_agent": False,
        "can_edit_settings": False,
        "can_manage_members": False,
        "can_manage_knowledge": False,
        "can_view_sensitive_data": False,  # ABSTRACTED / MASKED
        "can_edit_bookings": False,
        "can_delete_bookings": False,
        "can_call": True,
    },
}

def has_permission(role: str, perm_name: str) -> bool:
    role = (role or ROLE_VIEWER).lower()
    return PERMISSIONS.get(role, {}).get(perm_name, False)


# =====================================================================
# 2. SENSITIVE DATA ABSTRACTION & PII MASKING
# =====================================================================

def mask_name(name: str) -> str:
    """Masks person name while preserving title/first letter. E.g. John Doe -> J*** D***"""
    if not name:
        return ""
    parts = name.strip().split()
    masked_parts = []
    for p in parts:
        if p.lower() in {"dr.", "mr.", "mrs.", "ms.", "prof.", "dr", "mr", "mrs", "ms"}:
            masked_parts.append(p)
        elif len(p) <= 2:
            masked_parts.append(p[0] + "*")
        else:
            masked_parts.append(p[0] + "*" * (len(p) - 1))
    return " ".join(masked_parts)


def mask_phone(phone: str) -> str:
    """Masks phone number, keeping only the last 4 digits. E.g. +1 555 123 4567 -> ••••-•••-4567"""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if len(digits) <= 4:
        return "••••" + digits
    last_4 = digits[-4:]
    return "••••-•••-" + last_4


def abstract_room_notes(reason: str) -> str:
    """Abstracts specific confidential room notes, preferences, or medical details."""
    if not reason:
        return ""
    clean = reason.strip()
    # If the notes contain sensitive keywords, abstract them
    sensitive_markers = ["vip", "confidential", "medical", "doctor", "prescribe", "treatment", "passport", "card", "payment"]
    if any(m in clean.lower() for m in sensitive_markers):
        return "[Confidential Room Notes — Role Access Restricted]"
    # For standard reasons, summarize cleanly
    if len(clean) > 30:
        return clean[:27] + "..."
    return clean


def abstract_booking(booking: Dict[str, Any], role: str) -> Dict[str, Any]:
    """
    Applies guardrail abstraction to a booking dictionary based on the user's role.
    Owners and Managers receive full unredacted data.
    Receptionists, Viewers, and Public callers receive abstracted/masked data.
    """
    if not booking:
        return {}

    b = dict(booking)
    if has_permission(role, "can_view_sensitive_data"):
        b["_is_abstracted"] = False
        return b

    # Abstract sensitive personal and room information
    b["name"] = mask_name(b.get("name", ""))
    b["phone"] = mask_phone(b.get("phone", ""))
    b["reason"] = abstract_room_notes(b.get("reason", ""))
    b["_is_abstracted"] = True
    b["_role_level"] = role
    return b


# ── Phase G: Luhn check for card numbers ─────────────────────────────────────

def _luhn_check(digits: str) -> bool:
    """
    Return True if the digit string passes the Luhn algorithm.
    Used to reduce false-positive card redactions.
    """
    total = 0
    reverse_digits = digits[::-1]
    for i, ch in enumerate(reverse_digits):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def abstract_transcript(transcript: list, role: str) -> list:
    """Redacts PII patterns (phone numbers, card numbers, emails) from transcripts
    for lower-tier roles.

    Phase G changes:
    - Tokens now: [PHONE_REDACTED], [CARD_REDACTED], [EMAIL_REDACTED]
    - Phone regex: requires 10+ digits, skips booking IDs / dates / prices
    - Card regex: verifies Luhn before redacting
    - Added email redaction
    """
    if not transcript:
        return []
    if has_permission(role, "can_view_sensitive_data"):
        return transcript

    # ── Patterns ──────────────────────────────────────────────────────────────
    # Card: 13-19 digit groups (with spaces/dashes), validated with Luhn
    _card_pat = re.compile(r'\b(?:\d[ \-]*){13,19}\d\b')
    # Phone: international/national formats with 10+ digits total
    # Must start with + or (digits) — avoids dates like "2026-10-05" or prices like "$1,500"
    _phone_pat = re.compile(
        r'(?:(?:\+|00)[1-9]\d{0,2}[\s\-.]{0,2})?'
        r'(?:\(?\d{2,4}\)?[\s\-.]{0,2})'
        r'(?:\d{2,4}[\s\-.]{0,2}){2,4}\d{2,4}'
    )
    # Email
    _email_pat = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')

    out = []
    for turn in transcript:
        t = dict(turn)
        text = t.get("text") or t.get("content") or ""

        # Redact credit card numbers (Luhn-validated)
        def _redact_card(m: re.Match) -> str:
            digits = re.sub(r'\D', '', m.group(0))
            if 13 <= len(digits) <= 19 and _luhn_check(digits):
                return "[CARD_REDACTED]"
            return m.group(0)  # not a valid card — leave unchanged
        text = _card_pat.sub(_redact_card, text)

        # Redact phone numbers
        def _redact_phone(m: re.Match) -> str:
            digits = re.sub(r'\D', '', m.group(0))
            if len(digits) >= 10:
                return "[PHONE_REDACTED]"
            return m.group(0)
        text = _phone_pat.sub(_redact_phone, text)

        # Redact email addresses
        text = _email_pat.sub("[EMAIL_REDACTED]", text)

        if "text" in t:
            t["text"] = text
        if "content" in t:
            t["content"] = text
        out.append(t)
    return out



# =====================================================================
# 3. CONVERSATIONAL IN-CALL PRIVACY GUARDRAIL
# =====================================================================

PRIVACY_BREACH_PATTERNS = [
    # Queries attempting to uncover other guests' room numbers, reservations, or identities
    r"\bwho\s+(?:is|are)\s+(?:staying(?:\s+in)?|booked(?:\s+in|\s+for)?|in|checked\s+into)\s+(?:room|the\s+hotel|the\s+resort|the\s+clinic)",
    r"\bwho\s+(?:is|are)\s+in\s+room\s+\d+",
    r"\bwho\s+lives\s+in\s+room",
    r"\bwho\s+booked\s+(?:room|for|tomorrow|today|tonight)",
    r"\bgive\s+me\s+(?:the\s+)?(?:phone\s+number|names?|details?|address)\s+of\s+(?:the\s+)?(?:guest|caller|room|whoever)",
    r"\bwhat\s+(?:is|are)\s+(?:the\s+)?(?:names?|details?|phones?)\s+of\s+(?:other\s+guests|the\s+people\s+staying|room\s+\d+)",
    r"\bcan\s+you\s+(?:give|tell|reveal|show)\s+me\s+(?:all\s+the\s+bookings|other\s+bookings|guest\s+list|phone\s+numbers)",
    r"\bshow\s+me\s+(?:all\s+)?(?:the\s+)?(?:bookings|reservations|guests)",
    r"\bdump\s+(?:the\s+)?(?:database|bookings|database\s+table|records)",
    # Prompt injection attempts to exfiltrate system data
    r"\bignore\s+(?:all\s+)?previous\s+instructions\s+and\s+(?:tell|show|print|dump)",
    r"\bsystem\s+prompt\s+override",
    r"\brepeat\s+your\s+system\s+instructions",
]

COMPILED_BREACH_PATTERNS = [re.compile(p, re.IGNORECASE) for p in PRIVACY_BREACH_PATTERNS]

GUARDRAIL_BLOCKED_RESPONSE = (
    "For privacy and security, I cannot disclose personal guest details or internal reservation records. "
    "I am happy to help you with your own reservation or answer questions about our facilities!"
)

def evaluate_conversational_guardrail(user_text: str) -> Tuple[bool, Optional[str]]:
    """
    Checks incoming user utterance for data exfiltration or privacy violations.
    Returns (True, safe_response) if blocked, or (False, None) if approved.
    """
    if not user_text:
        return False, None

    text_lower = user_text.lower().strip()

    for pattern in COMPILED_BREACH_PATTERNS:
        if pattern.search(text_lower):
            print(f"🛡️ [GUARDRAIL INTERCEPT] Blocked privacy inquiry: '{user_text}'")
            return True, GUARDRAIL_BLOCKED_RESPONSE

    return False, None
