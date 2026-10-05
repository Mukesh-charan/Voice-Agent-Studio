"""
Generate MS Resort Official Operational Data & Guest Guide PDF.
This document contains complete room inventory, numbering rules, pricing structure,
amenities, scheduled facilities, booking protocol, and receptionist knowledge base data.
"""

import fitz

def generate_pdf(output_path="ms_resort_guide.pdf"):
    doc = fitz.open()

    # Define color scheme (RGB 0-1)
    NAVY = (0.08, 0.18, 0.36)
    GOLD = (0.78, 0.60, 0.20)
    DARK_GRAY = (0.2, 0.2, 0.2)
    LIGHT_BG = (0.95, 0.96, 0.98)
    LINE_COLOR = (0.85, 0.85, 0.85)

    # Page 1: Overview, Room Inventory & Pricing Structure
    page1 = doc.new_page(width=595, height=842) # A4
    
    # Header Banner
    header_rect = fitz.Rect(0, 0, 595, 80)
    page1.draw_rect(header_rect, color=None, fill=NAVY)
    page1.insert_text(fitz.Point(40, 48), "MS RESORT -- RESORT DIRECTORY & OPERATIONAL GUIDE", fontsize=14, color=(1, 1, 1), fontname="hebo")
    page1.insert_text(fitz.Point(40, 68), "Official Front Desk, Knowledge Base & Voice Receptionist Operations Manual", fontsize=9, color=GOLD, fontname="helv")

    y = 110

    def draw_section_heading(p, text, cur_y):
        rect = fitz.Rect(40, cur_y, 555, cur_y + 24)
        p.draw_rect(rect, color=None, fill=LIGHT_BG)
        p.draw_line(fitz.Point(40, cur_y), fitz.Point(40, cur_y + 24), color=NAVY, width=3)
        p.insert_text(fitz.Point(48, cur_y + 16), text, fontsize=11, color=NAVY, fontname="hebo")
        return cur_y + 36

    # Section 1: Overview
    y = draw_section_heading(page1, "1. EXECUTIVE OVERVIEW & VOICE RECEPTIONIST IDENTITY", y)
    overview_text = (
        "Welcome to MS Resort. This operational guide provides comprehensive information for staff, "
        "guests, and dedicated voice receptionists (Ramya).\n\n"
        "- Dedicated Receptionist: Ramya\n"
        "- Primary Function: Handle guest inquiries, provide facility details, verify room availability, and manage reservations.\n"
        "- Standard Greeting: \"Hello, this is Ramya speaking from MS Resort. How may I assist you today?\"\n"
        "- Demeanor: Warm, courteous, calm, conversational, and professional at all times."
    )
    page1.insert_textbox(fitz.Rect(40, y, 555, y + 80), overview_text, fontsize=9.5, fontname="helv", color=DARK_GRAY)
    y += 90

    # Section 2: Room Inventory & Numbering
    y = draw_section_heading(page1, "2. ROOM INVENTORY & NUMBERING STRUCTURE", y)
    inventory_text = (
        "MS Resort consists of four (4) residential floors with ten (10) luxury rooms on each floor, totaling 40 rooms.\n"
        "Room numbers are systematically formatted as a three-digit code (e.g., 101 to 410):\n"
        "  * First Digit (1 to 4): Indicates the floor level (Floor 1, Floor 2, Floor 3, or Floor 4).\n"
        "  * Next Two Digits (01 to 10): Represent the specific room position on that floor.\n"
        "  * Example: Room 109 is located on Floor 1, Room position 09. Room 304 is on Floor 3, Room position 04."
    )
    page1.insert_textbox(fitz.Rect(40, y, 555, y + 80), inventory_text, fontsize=9.5, fontname="helv", color=DARK_GRAY)
    y += 85

    # Section 3: Room Categories & Pricing Table
    y = draw_section_heading(page1, "3. ROOM CATEGORIES, CAPACITY & TARIFFS", y)
    
    # Table Header
    th_rect = fitz.Rect(40, y, 555, y + 20)
    page1.draw_rect(th_rect, color=NAVY, fill=NAVY)
    page1.insert_text(fitz.Point(45, y + 14), "Category", fontsize=9, color=(1, 1, 1), fontname="hebo")
    page1.insert_text(fitz.Point(175, y + 14), "Room Positions (Each Floor)", fontsize=9, color=(1, 1, 1), fontname="hebo")
    page1.insert_text(fitz.Point(340, y + 14), "Max Capacity", fontsize=9, color=(1, 1, 1), fontname="hebo")
    page1.insert_text(fitz.Point(440, y + 14), "Rate (Per Day & Night)", fontsize=9, color=(1, 1, 1), fontname="hebo")
    y += 20

    rows = [
        ("Two-Person Suite", "Positions 01, 02, 03 (e.g., 101, 102, 103)", "2 Persons", "Rs. 3,000 / day & night"),
        ("Deluxe Room", "Positions 04, 05, 06, 07 (e.g., 104-107)", "4 Persons", "Rs. 6,000 / day & night"),
        ("Super Deluxe Room", "Positions 08, 09, 10 (e.g., 108, 109, 110)", "4 Persons (Executive)", "Rs. 10,000 / day & night")
    ]

    for i, (cat, pos, cap, rate) in enumerate(rows):
        bg = LIGHT_BG if i % 2 == 1 else (1, 1, 1)
        r_rect = fitz.Rect(40, y, 555, y + 24)
        page1.draw_rect(r_rect, color=LINE_COLOR, fill=bg)
        page1.insert_text(fitz.Point(45, y + 16), cat, fontsize=9, color=NAVY, fontname="hebo")
        page1.insert_text(fitz.Point(175, y + 16), pos, fontsize=8.5, color=DARK_GRAY, fontname="helv")
        page1.insert_text(fitz.Point(340, y + 16), cap, fontsize=9, color=DARK_GRAY, fontname="helv")
        page1.insert_text(fitz.Point(440, y + 16), rate, fontsize=9, color=NAVY, fontname="hebo")
        y += 24

    y += 20
    # Spoken rules reminder
    pricing_note = (
        "Note on Spoken Rates: When quoting prices to callers, always speak the currency amount clearly: "
        "say 'three thousand rupees', 'six thousand rupees', and 'ten thousand rupees' instead of numeric abbreviations."
    )
    page1.insert_textbox(fitz.Rect(40, y, 555, y + 40), pricing_note, fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
    
    # Page 1 Footer
    page1.insert_text(fitz.Point(40, 815), "MS Resort Operational Guide -- Page 1 of 2", fontsize=8, color=(0.5, 0.5, 0.5), fontname="helv")
    page1.insert_text(fitz.Point(440, 815), "Confidential -- Internal Operations", fontsize=8, color=(0.5, 0.5, 0.5), fontname="helv")

    # ==========================================
    # Page 2: Amenities, Booking Protocol & Policies
    # ==========================================
    page2 = doc.new_page(width=595, height=842)
    
    # Page 2 Header Banner
    header_rect2 = fitz.Rect(0, 0, 595, 50)
    page2.draw_rect(header_rect2, color=None, fill=NAVY)
    page2.insert_text(fitz.Point(40, 32), "MS RESORT -- AMENITIES, BOOKING PROTOCOL & VOICE GUIDELINES", fontsize=11, color=(1, 1, 1), fontname="hebo")

    y2 = 70

    # Section 4: Facilities & Amenities
    y2 = draw_section_heading(page2, "4. FACILITIES, SERVICES & OPERATING TIMINGS", y2)
    amenities_text = (
        "MS Resort provides a comprehensive range of premium hospitality amenities for registered guests:\n\n"
        "1. Comprehensive Room Service: Includes daily housekeeping, in-room dining and food delivery, luggage assistance, "
        "and 24-hour concierge support.\n\n"
        "2. Full-Service Multi-Cuisine Restaurant: On-site restaurant operating strictly on fixed scheduled timings "
        "(Breakfast, Lunch, and Dinner). Inform guests of scheduled meal hours and note preferred dining windows.\n\n"
        "3. Swimming Pool: Accessible on a properly scheduled basis with dedicated adult and family swim sessions. "
        "Guests should verify daily pool schedules upon arrival.\n\n"
        "4. Complimentary Wi-Fi: High-speed wireless internet access available across all guest rooms, suites, and public resort areas.\n\n"
        "5. On-Site Parking: Secure, complimentary on-site parking for all staying guests."
    )
    page2.insert_textbox(fitz.Rect(40, y2, 555, y2 + 180), amenities_text, fontsize=9.2, fontname="helv", color=DARK_GRAY)
    y2 += 190

    # Section 5: Booking Protocol
    y2 = draw_section_heading(page2, "5. STEP-BY-STEP RESERVATION PROTOCOL", y2)
    protocol_text = (
        "When handling reservation inquiries, the receptionist must follow this sequential three-step procedure:\n\n"
        "- Step 1: Availability Check -- Verify requested room type and stay dates before collecting personal information. "
        "If dates are not specified, ask for check-in and check-out dates. Offer alternative dates or categories if full.\n\n"
        "- Step 2: Lead Capture -- Once availability is confirmed, capture details one question at a time:\n"
        "    1. Guest's Full Name (e.g., 'May I have your full name please?')\n"
        "    2. Guest's Contact Phone Number\n"
        "    3. Confirm specific room category (Two-Person Suite, Deluxe, or Super Deluxe)\n\n"
        "- Step 3: Confirmation & Readback -- Read back all details: Guest Name, Phone Number, Room Category, "
        "Check-in/Check-out Dates, and Total Tariff. Request verbal confirmation before finalizing."
    )
    page2.insert_textbox(fitz.Rect(40, y2, 555, y2 + 180), protocol_text, fontsize=9.2, fontname="helv", color=DARK_GRAY)
    y2 += 190

    # Section 6: Correction Handling & Guidelines
    y2 = draw_section_heading(page2, "6. CORRECTIONS & VOICE INTERACTION GUIDELINES", y2)
    guidelines_text = (
        "- Correction Handling: If a guest corrects previously provided details (e.g., misspelled name or revised phone number), "
        "immediately update the record without repeating the mistake. Acknowledge briefly and resume flow.\n"
        "- Spoken Formatting: Speak naturally. Do not utter markdown symbols, asterisks, bullet points, or raw numbers.\n"
        "- Turn Length: Maintain 1 to 3 concise conversational sentences per turn.\n"
        "- Unknown Inquiries: Politely state lack of information and offer manager callback or message taking."
    )
    page2.insert_textbox(fitz.Rect(40, y2, 555, y2 + 110), guidelines_text, fontsize=9.2, fontname="helv", color=DARK_GRAY)

    # Page 2 Footer
    page2.insert_text(fitz.Point(40, 815), "MS Resort Operational Guide -- Page 2 of 2", fontsize=8, color=(0.5, 0.5, 0.5), fontname="helv")
    page2.insert_text(fitz.Point(440, 815), "Confidential -- Internal Operations", fontsize=8, color=(0.5, 0.5, 0.5), fontname="helv")

    doc.save(output_path)
    doc.close()
    print(f"Successfully generated {output_path}")

if __name__ == "__main__":
    generate_pdf()
