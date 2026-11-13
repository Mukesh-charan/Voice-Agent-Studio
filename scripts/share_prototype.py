"""
Share Prototype — Voice Agent Studio Collaboration Utility
Allows team members to work together on the same prototype simultaneously.
"""

import socket
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def main():
    local_ip = get_local_ip()
    port = 8001
    
    print("=" * 65)
    print(" [VOICE AGENT STUDIO] COLLABORATIVE PROTOTYPE ENVIRONMENT")
    print("=" * 65)
    print()
    print("1. LOCAL / SAME WI-FI COLLABORATION:")
    print(f"   Host Computer:      http://localhost:{port}")
    print(f"   Teammate / Phone:   http://{local_ip}:{port}")
    print()
    print("   Both users can log in using the same account credentials.")
    print("   Agent configuration, prompts, and bookings sync instantly!")
    print()
    print("2. REMOTE COLLABORATION (DIFFERENT WI-FI / OVER THE INTERNET):")
    print("   To test from anywhere (home, mobile cellular data):")
    print(f"   Option A (Cloudflare Tunnel - Free, No sign up):")
    print(f"     npx untun@latest tunnel --port {port}")
    print(f"   Option B (Localtunnel):")
    print(f"     npx localtunnel --port {port}")
    print()
    print("   This gives you a public HTTPS URL with valid SSL so microphone")
    print("   permissions work seamlessly on mobile Safari and Chrome!")
    print("=" * 65)

if __name__ == "__main__":
    main()
