"""
Voice Agent Studio — Booking Engine.
Handles booking tool schemas, calendar truth tables, relative datetime resolution,
intent activation heuristics, inline JSON tool parsing, and input guardrail verification.
"""

import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "save_booking",
        "description": (
            "Save and finalize a guest's resort or room reservation into the database. "
            "ONLY invoke after the caller has explicitly shared their name, dates, room choice, and verbally confirmed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Full legal name of the primary guest (e.g. 'Sanjjey Arumugam')."
                },
                "phone": {
                    "type": "string",
                    "description": "Guest contact telephone or mobile number."
                },
                "datetime": {
                    "type": "string",
                    "description": "Check-in date or arrival timeframe (e.g. 'Tomorrow', '2026-10-14', 'Friday 2:00 PM')."
                },
                "reason": {
                    "type": "string",
                    "description": "Room type reserved, number of guests, or special requirements (e.g. 'Two-Person Suite, 2 guests')."
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "True if the guest gave explicit verbal confirmation to proceed."
                }
            },
            "required": ["name", "datetime"]
        }
    }
}

UPDATE_BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "update_booking",
        "description": "Update an existing reservation with modified dates, guest count, or room selection.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {
                    "type": "integer",
                    "description": "Numeric ID of the existing booking to modify."
                },
                "datetime": {
                    "type": "string",
                    "description": "Updated check-in date or arrival time."
                },
                "reason": {
                    "type": "string",
                    "description": "Updated room details or guest notes."
                }
            }
        }
    }
}

BOOKING_SYSTEM_GUARDRAIL = (
    "\n\n# STRICT RESERVATION & BOOKING CONVERSATION RULES:\n"
    "1. GUEST INQUIRIES: When a guest asks about rooms, pricing, or facilities, answer clearly and conversationally. "
    "DO NOT attempt to finalize or save a booking during initial inquiries.\n"
    "2. GATHERING INFORMATION: When the guest expresses interest in booking, ask one question at a time:\n"
    "   - First ask for their desired check-in and check-out dates.\n"
    "   - Next ask for the guest's full name.\n"
    "   - Next ask for their contact phone number.\n"
    "3. EXPLICIT CONFIRMATION: Summarize the reservation details (name, dates, room category) and ask: "
    "'Would you like me to confirm this booking for you?'\n"
    "4. FINALIZING: You may ONLY call the save_booking function after the guest explicitly says yes or confirms.\n"
    "5. NEVER use your own name (the receptionist), 'guest's full name', 'null', or placeholders as the guest's name.\n"
    "6. DATES: When the guest says 'tomorrow', map it to tomorrow's exact calendar date (the day after today), NEVER today's date."
)


def build_calendar_prompt() -> str:
    """Builds a real-time calendar truth table so the LLM maps relative days without hallucination."""
    now = datetime.now()
    today_str = now.strftime("%A, %B %d, %Y")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%A, %B %d, %Y")
    day_after = now + timedelta(days=2)
    day_after_str = day_after.strftime("%A, %B %d, %Y")

    return (
        f"\n\n# REAL-TIME CALENDAR TRUTH TABLE (MANDATORY EXACT MATCH):\n"
        f"• TODAY: {today_str}\n"
        f"• TOMORROW: {tomorrow_str}\n"
        f"• DAY AFTER TOMORROW: {day_after_str}\n"
        f"• CURRENT TIME: {now.strftime('%I:%M %p')}\n"
        f"Always map 'tomorrow' or 'today' into these exact calendar dates."
    )


def resolve_booking_datetime(raw_dt: str) -> str:
    """Resolves colloquial spoken date expressions ('tomorrow', 'Saturday') into calendar strings."""
    if not raw_dt:
        return ""
    s = raw_dt.lower().strip()
    today = datetime.now().date()
    fmt = "%A, %b %d, %Y"

    # Multi-day checks e.g. "tomorrow and day after tomorrow", "2 nights"
    if ("tomorrow" in s and any(k in s for k in [" to ", " and ", " until ", " through ", " - "]) and ("after" in s or "next" in s)) or "2 night" in s or "two night" in s:
        d1 = today + timedelta(days=1)
        d2 = today + timedelta(days=2)
        return f"{d1.strftime(fmt)} to {d2.strftime(fmt)}"

    if "day after tomorrow" in s or "after tomorrow" in s:
        return (today + timedelta(days=2)).strftime(fmt)

    if "tomorrow" in s:
        target = today + timedelta(days=1)
        time_m = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", s)
        time_str = f" at {time_m.group(1)}" if time_m else ""
        return target.strftime(fmt) + time_str

    if "today" in s or "tonight" in s:
        return today.strftime(fmt)

    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for idx, dname in enumerate(days):
        if dname in s:
            cur_weekday = today.weekday()
            diff = (idx - cur_weekday) % 7
            if diff == 0:
                diff = 7
            return (today + timedelta(days=diff)).strftime(fmt)

    return raw_dt.strip()


def should_enable_booking_tools(messages: list) -> bool:
    """Prevents LLM from prematurely invoking save_booking during initial general inquiries."""
    if not messages:
        return False

    user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
    if not user_texts:
        return False

    combined_user = " ".join(user_texts).lower()

    date_indicators = [
        "today", "tomorrow", "tonight", "night", "nights", "day", "days",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "next week", "weekend", "pm", "am", "clock", "check in", "check-in"
    ]
    has_date = any(w in combined_user for w in date_indicators) or bool(re.search(r"\b\d{1,2}(st|nd|rd|th|\s*(?:am|pm)|[/-]\d{1,2})\b", combined_user))

    clean_digits = re.sub(r"[^\d]", "", combined_user)
    has_phone = len(clean_digits) >= 6 or bool(re.search(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", combined_user))
    has_name = any(kw in combined_user for kw in ["my name is", "i'm ", "i am ", "this is ", "name's ", "name is"]) or len(user_texts) >= 3

    confirm_keywords = ["confirm", "proceed", "go ahead", "book", "finalize", "yes please", "yes, please", "sure, book", "reserve"]
    has_confirm = any(k in combined_user for k in confirm_keywords)

    if (has_date and (has_name or has_phone)) or (has_confirm and (has_date or has_phone)):
        return True

    return False


def extract_inline_tool_call(content: str) -> Tuple[Optional[str], Optional[dict]]:
    """Detects raw JSON tool calls emitted directly in stream content by models like Ollama."""
    if not content:
        return None, None
    s = content.strip()
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.DOTALL)
    if match:
        s = match.group(1).strip()
    elif s.startswith("{") and s.endswith("}"):
        pass
    else:
        m2 = re.search(r"(\{[\s\S]*\})", s)
        if m2:
            s = m2.group(1).strip()
        else:
            return None, None

    try:
        data = json.loads(s)
        if not isinstance(data, dict):
            return None, None
        if "name" in data and ("arguments" in data or "parameters" in data):
            fn_name = data["name"]
            args = data.get("arguments") or data.get("parameters") or {}
            if isinstance(args, str):
                args = json.loads(args)
            return fn_name, args
        if any(k in data for k in ["name", "datetime", "room_type", "reason", "phone"]):
            return "save_booking", data
        if "booking_id" in data:
            return "update_booking", data
    except Exception:
        pass
    return None, None


def validate_booking_name(raw_name: str, agent: Optional[dict], messages: Optional[list]) -> Tuple[bool, str]:
    """
    Validates guest name against placeholders and bot persona names,
    with phonetic / fuzzy similarity tolerance against Whisper STT variations.
    """
    clean_name = raw_name.lower().strip(" .!?,<>()[]{}\"\'")
    placeholder_terms = [
        "guest", "caller", "null", "none", "unknown", "user", "test", "tester",
        "n/a", "undefined", "anonymous", "full name", "contact", "phone number",
        "not specified", "unspecified", "someone", "customer", "placeholder", "no name"
    ]
    if not clean_name or any(p in clean_name for p in placeholder_terms):
        return False, "Caller's real name is missing or is a placeholder."
    if len(clean_name) < 2 or not any(c.isalpha() for c in clean_name):
        return False, "Caller's real name must contain valid letters."

    if agent:
        agent_name = (agent.get("name") or "").strip().lower()
        if agent_name and clean_name == agent_name:
            return False, f"Cannot use '{raw_name}' because that is the receptionist/bot name, not the guest's name."
        prompt_lower = (agent.get("system_prompt") or "").lower()
        if f"name is {clean_name}" in prompt_lower or f"i am {clean_name}" in prompt_lower or f"this is {clean_name}" in prompt_lower:
            return False, f"Cannot use '{raw_name}' because that is your assistant persona name, not the guest's name."

    if messages:
        user_texts = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"]).lower()
        user_words = set(re.findall(r"\b[a-zA-Z]{2,}\b", user_texts.lower()))
        name_parts = [p.lower() for p in re.findall(r"\b[a-zA-Z]{2,}\b", raw_name) if p.lower() not in {"mr", "mrs", "ms", "dr", "name", "is", "my", "the"}]

        # Direct token match or fuzzy / phonetic tolerance (e.g. 'sande' vs 'sanjjey')
        matched = False
        if any(part in user_words for part in name_parts):
            matched = True
        else:
            for part in name_parts:
                for uw in user_words:
                    if part.startswith(uw[:3]) or uw.startswith(part[:3]):
                        matched = True
                        break
                    if abs(len(part) - len(uw)) <= 2 and SequenceMatcher(None, part, uw).ratio() >= 0.65:
                        matched = True
                        break
                if matched:
                    break

        if not matched:
            return False, "The caller has not shared their name in the conversation yet. Please ask: 'May I have your full name?' before booking."

    return True, ""
