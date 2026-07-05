# Local Wi-Fi Voice App Architecture

## Objective

The AI engine already exists:

``` text
Audio Input
    ↓
Speech-to-Text (STT)
    ↓
Groq LLM
    ↓
Text-to-Speech (TTS)
    ↓
Audio Output
```

**Do not modify the AI engine.**

The objective is to build a transport layer that allows a mobile phone
connected to the same Wi-Fi network (or later the Internet) to
communicate with the AI through real-time voice.

------------------------------------------------------------------------

# Overall Architecture

``` text
                Wi-Fi Router
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
  Android / iOS App         Laptop Server
     (Voice Client)         (Voice Agent)
         │                       │
         └──── WebRTC (Preferred)┘
                  or WebSocket
                     │
                     ▼
          Audio Transport Layer
                     │
                     ▼
             STT → Groq → TTS
                     │
                     ▼
               Audio Response
                     │
                     ▼
              Mobile Application
```

------------------------------------------------------------------------

# Functional Flow

1.  User opens the mobile application.
2.  User presses **Call AI**.
3.  The app discovers or connects to the laptop's server IP.
4.  A voice session is created.
5.  The mobile app continuously streams microphone audio.
6.  The server forwards the audio to the existing STT engine.
7.  The STT transcript is sent to Groq.
8.  Groq generates a response.
9.  The response is synthesized using the existing TTS engine.
10. Audio is streamed back to the mobile app.
11. The mobile app immediately plays the received audio.
12. Steps 5--11 repeat until the session ends.

------------------------------------------------------------------------

# Components

## Mobile Application

Responsibilities:

-   Call AI button
-   Capture microphone audio
-   Play streamed audio
-   Maintain connection
-   Display connection status
-   Handle reconnects

------------------------------------------------------------------------

## Connection Layer

Preferred protocol:

-   WebRTC (low latency, bidirectional audio)

Alternative:

-   WebSocket audio streaming

Responsibilities:

-   Session creation
-   Audio transport
-   Packet ordering
-   Connection management

------------------------------------------------------------------------

## Laptop Server

Responsibilities:

-   Accept client connections
-   Manage multiple sessions
-   Stream audio to STT
-   Send transcripts to Groq
-   Stream text to TTS
-   Return synthesized audio

------------------------------------------------------------------------

## Existing AI Engine

This remains unchanged.

``` text
Incoming Audio
      │
      ▼
STT
      ▼
Groq
      ▼
TTS
      ▼
Outgoing Audio
```

The transport layer must only provide audio input and consume audio
output.

------------------------------------------------------------------------

# Recommended Project Structure

``` text
voice-platform/
│
├── mobile-app/
│
├── backend/
│   ├── api/
│   ├── session_manager/
│   ├── transport/
│   ├── ai_engine/
│   └── main.py
│
└── docs/
```

------------------------------------------------------------------------

# Session Lifecycle

``` text
User Opens App
        │
Press Call AI
        │
Create Session
        │
Start Audio Streaming
        │
Conversation Loop
        │
User Ends Call
        │
Close Streams
        │
Destroy Session
```

------------------------------------------------------------------------

# Multiple Users

Each caller must have an isolated session.

``` text
Phone A → Session A → STT → Groq → TTS

Phone B → Session B → STT → Groq → TTS

Phone C → Session C → STT → Groq → TTS
```

No conversation state should be shared.

------------------------------------------------------------------------

# Future Upgrade Path

The backend should be transport-agnostic.

Current transport:

``` text
Mobile App
    │
WebRTC/WebSocket
```

Future transport:

``` text
SIP Trunk
     │
Asterisk PBX
```

The AI engine, session manager, and business logic should require no
changes when replacing the transport layer.

------------------------------------------------------------------------

# Deliverables for Implementation

-   Mobile app with "Call AI"
-   Real-time microphone capture
-   Real-time audio playback
-   WebRTC (preferred) or WebSocket transport
-   Backend session manager
-   Audio streaming service
-   Integration with existing STT → Groq → TTS engine
-   Multi-session support
-   Clean connection and disconnection handling
-   Modular architecture suitable for future SIP/Asterisk integration
