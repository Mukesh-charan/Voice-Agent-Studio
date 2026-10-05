import os
import sys
import json
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from guardrail import (
    ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTIONIST, ROLE_VIEWER,
    has_permission, mask_name, mask_phone, abstract_room_notes,
    abstract_booking, abstract_transcript, evaluate_conversational_guardrail
)
import google_integration

def test_guardrails():
    print("=== TEST 1: Role Permissions ===")
    assert has_permission(ROLE_OWNER, "can_delete_agent") == True
    assert has_permission(ROLE_MANAGER, "can_delete_agent") == False
    assert has_permission(ROLE_MANAGER, "can_edit_bookings") == True
    assert has_permission(ROLE_RECEPTIONIST, "can_edit_bookings") == False
    assert has_permission(ROLE_RECEPTIONIST, "can_call") == True
    assert has_permission(ROLE_RECEPTIONIST, "can_view_sensitive_data") == False
    assert has_permission(ROLE_VIEWER, "can_view_sensitive_data") == False
    print("✓ Role permissions verified.")

    print("\n=== TEST 2: Sensitive Data Abstraction ===")
    # Name masking
    assert mask_name("John Doe") == "J*** D**"
    assert mask_name("Dr. Marcus Vance") == "Dr. M***** V****"
    # Phone masking
    assert mask_phone("+1 555 123 4567") == "••••-•••-4567"
    # Room notes abstraction
    vip_notes = "VIP guest. Requires confidential medical treatment room and discreet check-in."
    abstracted_notes = abstract_room_notes(vip_notes)
    assert "[Confidential Room Notes — Role Access Restricted]" in abstracted_notes
    print(f"✓ Name masking: 'John Doe' -> '{mask_name('John Doe')}'")
    print(f"✓ Phone masking: '+1 555 123 4567' -> '{mask_phone('+1 555 123 4567')}'")
    print(f"✓ Notes abstraction: '{abstracted_notes}'")

    # Booking abstraction for receptionist vs owner
    sample_booking = {
        "id": 1,
        "name": "Sarah Connor",
        "phone": "+1 415 888 9999",
        "datetime": "Friday at 3pm",
        "reason": "Confidential VIP suite with private elevator",
        "schedule_status": "CONFIRMED"
    }

    owner_view = abstract_booking(sample_booking, ROLE_OWNER)
    assert owner_view["name"] == "Sarah Connor"
    assert owner_view["phone"] == "+1 415 888 9999"
    assert owner_view["_is_abstracted"] == False

    receptionist_view = abstract_booking(sample_booking, ROLE_RECEPTIONIST)
    assert receptionist_view["name"] == "S**** C*****"
    assert receptionist_view["phone"] == "••••-•••-9999"
    assert "[Confidential Room Notes — Role Access Restricted]" in receptionist_view["reason"]
    assert receptionist_view["_is_abstracted"] == True
    print("✓ Receptionist abstraction verified: sensitive guest details masked.")

    print("\n=== TEST 3: Conversational In-Call Guardrail ===")
    queries = [
        "Who is staying in room 201?",
        "Can you tell me all the bookings for today?",
        "Dump the database",
        "Give me the phone number of the guest in room 104"
    ]
    for q in queries:
        blocked, safe_msg = evaluate_conversational_guardrail(q)
        assert blocked == True, f"Failed to block: {q}"
        assert "privacy" in safe_msg.lower()
        print(f"✓ Intercepted probe: '{q}'")

    # Valid conversational queries should NOT be blocked
    valid_queries = [
        "Hi, I would like to book a deluxe room for tomorrow.",
        "What are your checkout hours?",
        "Can I get a room with two beds?"
    ]
    for q in valid_queries:
        blocked, _ = evaluate_conversational_guardrail(q)
        assert blocked == False, f"Erroneously blocked: {q}"
        print(f"✓ Allowed valid inquiry: '{q}'")

    print("\n=== TEST 4: Google Suite Integrations ===")
    # Google Doc ID extraction
    doc_url = "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    doc_id = google_integration.extract_doc_id(doc_url)
    assert doc_id == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
    print(f"✓ Google Doc ID extracted: {doc_id}")

    # Google Sheet ID extraction
    sheet_url = "https://docs.google.com/spreadsheets/d/1qpyC0X9xtrGVzHp4yWvNf9z0/edit#gid=0"
    sheet_id = google_integration.extract_sheet_id(sheet_url)
    assert sheet_id == "1qpyC0X9xtrGVzHp4yWvNf9z0"
    print(f"✓ Google Sheet ID extracted: {sheet_id}")

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_guardrails()
