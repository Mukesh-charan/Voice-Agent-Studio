# Voice-Agent Runtime Appliance — Tech Stack & System Requirements Spec

**Status:** draft v1
**Scope:** the self-hosted runtime that deploys inside a customer's VPC and runs outbound/inbound AI phone calls. All conversation processing (STT, LLM, TTS) stays inside the customer network. Only raw call audio leaves the box (to the carrier) and config/metering to the control plane.

---

## 1. Design principles

1. **Data plane stays local.** Transcripts, LLM, knowledge base, recordings never leave the customer VPC.
2. **GPU is mandatory.** Conversational latency is impossible to hit reliably on CPU-only inference. The spec assumes one NVIDIA GPU minimum.
3. **One supported deployment path first:** Ubuntu Linux + Docker Compose + NVIDIA GPU. Helm/k8s is a later target.
4. **Bring-your-own carrier.** Customer supplies their own Twilio (or SIP trunk) credentials. Keeps you out of their telecom compliance and keeps numbers under their account.
5. **Stream everything.** No stage waits for a previous stage to fully finish. This is the difference between "feels human" and "feels like a 2010 IVR."

---

## 2. System architecture (services)

```
                       Customer VPC (the appliance)
┌──────────────────────────────────────────────────────────────────┐
│                                                                    │
│   ┌──────────────┐   WebSocket    ┌──────────────────────────┐    │
│   │ telephony-   │ ◄────audio────►│ orchestrator             │    │
│   │ bridge       │  (8k μ-law)    │ (Pipecat pipeline)       │    │
│   │ (Twilio MS / │                │  • VAD / endpointing     │    │
│   │  SIP gw)     │                │  • turn-taking, barge-in │    │
│   └──────┬───────┘                │  • tool calls            │    │
│          │                        └───┬──────┬──────┬────────┘    │
│          │                            │      │      │             │
│          │                       gRPC/HTTP local loopback         │
│          │                            ▼      ▼      ▼             │
│          │                       ┌──────┐┌──────┐┌──────┐         │
│          │                       │ STT  ││ LLM  ││ TTS  │         │
│          │                       │whisper││vLLM  ││Kokoro│         │
│          │                       └──────┘└──────┘└──────┘         │
│          │                                                         │
│   ┌──────┴───────┐   ┌──────────┐  ┌───────┐  ┌──────────────┐    │
│   │ Postgres     │   │ Redis    │  │ MinIO │  │ Prometheus + │    │
│   │ (config,logs)│   │ (state)  │  │ (recs)│  │ Grafana      │    │
│   └──────────────┘   └──────────┘  └───────┘  └──────────────┘    │
│                                                                    │
└───────────┬────────────────────────────────────────┬──────────────┘
            │ raw call audio only                     │ config pull + usage metering
            ▼                                          ▼
     Carrier (Twilio/SIP) ⇄ PSTN              Your control-plane cloud
```

---

## 3. Software stack (concrete choices)

| Layer | Recommended | Why / notes | Alternatives |
|---|---|---|---|
| **OS** | Ubuntu 22.04 / 24.04 LTS | Best NVIDIA + Docker support | RHEL 9 (later) |
| **Container runtime** | Docker 26+ + Docker Compose v2 | Single supported path | Podman, k8s/Helm (later) |
| **GPU runtime** | NVIDIA driver 550+, CUDA 12.4+, NVIDIA Container Toolkit | Required for all inference containers | — |
| **Orchestration framework** | **Pipecat** (open source, Python/asyncio) | Purpose-built for realtime voice agents; native Twilio Media Streams support; pluggable local STT/LLM/TTS; handles VAD, interruption, turn-taking — this is the open-source equivalent of Vapi's core | LiveKit Agents; custom asyncio |
| **Telephony bridge** | Twilio Media Streams over WebSocket (BYO creds) | `<Connect><Stream>` TwiML → WS to bridge | SIP trunk via Jambonz/Drachtio; LiveKit SIP |
| **VAD / endpointing** | Silero VAD + Pipecat smart-turn | Cheap, accurate end-of-speech detection | WebRTC VAD (worse) |
| **STT** | **faster-whisper** (CTranslate2) running `large-v3-turbo`, GPU | Streaming, ~1.5–4 GB VRAM, strong accuracy/latency | NVIDIA Parakeet/Canary (NeMo); Deepgram **on-prem** container (paid, excellent latency) |
| **LLM serving** | **vLLM** (OpenAI-compatible server) | Best concurrency via continuous batching; low TTFT; streams tokens | Ollama (simpler, lower concurrency); TGI; SGLang |
| **LLM model** | `Llama-3.1-8B-Instruct` or `Qwen2.5-7B/14B-Instruct`, FP8/AWQ quant | 8B sweet spot for latency on 24 GB; 14B if VRAM allows | Mistral-Nemo-12B; phi-4 |
| **TTS** | **Kokoro-82M** (streaming) | Fast, high quality, tiny VRAM (~1–2 GB), good for realtime | Piper (fastest, lower quality); Orpheus-TTS (more natural, heavier); XTTS-v2 (voice cloning, slower) |
| **Config DB** | PostgreSQL 16 | Agent configs, call metadata, transcripts (local) | — |
| **State / cache** | Redis 7 | Live call state, session, rate limits | — |
| **Recording store** | MinIO (S3-compatible, local) | Recordings/transcripts stay in-VPC; optional, off by default | Local disk |
| **Metrics** | Prometheus + Grafana | Latency, concurrency, GPU util dashboards | — |
| **Logs** | Structured JSON → Loki (optional) | Customer-readable diagnostics (no SSH access for you) | Docker json-file + dashboard |
| **Control-plane agent** | Lightweight "config + license" sidecar | Pulls signed agent config; reports usage minutes (no content) | Air-gap import mode |

---

## 4. The realtime audio pipeline (formats matter)

| Stage | Format | Notes |
|---|---|---|
| Twilio Media Streams in | **8 kHz μ-law (G.711)**, base64 in JSON, 20 ms frames (160 bytes) | Over WebSocket |
| → STT input | resample to **16 kHz PCM s16le** | μ-law decode + upsample |
| LLM | text tokens (streamed) | — |
| TTS output | model-native (often 24 kHz) | — |
| → Twilio out | downsample to **8 kHz μ-law**, 20 ms frames | base64 back over WS |

**Barge-in handling:** when VAD detects caller speech during bot playback, orchestrator must (1) stop pulling TTS, (2) send a Twilio `clear` message to flush queued audio, (3) cancel the in-flight LLM/TTS turn. Pipecat handles this; verify it on real calls.

---

## 5. Latency budget (target: < 800 ms end-of-speech → bot speaks)

| Segment | Budget | How to hit it |
|---|---|---|
| Endpointing (detect end of speech) | 150–250 ms | Silero VAD + tuned silence timeout |
| STT finalization | 50–150 ms | faster-whisper partial/final on GPU |
| LLM time-to-first-token | 150–350 ms | vLLM, 8B FP8, short system prompt, warm model |
| TTS time-to-first-audio | 80–200 ms | Kokoro streaming, emit on first sentence |
| Network + Twilio | ~100 ms | colocate bridge near carrier region |
| **Total perceived** | **~600–900 ms** | overlap stages; never serialize |

**Rule:** start TTS on the first sentence while the LLM is still generating; start streaming audio to Twilio on the first TTS chunk.

---

## 6. Hardware / system requirements (tiered)

> All tiers assume **NVIDIA GPU + CUDA**. CPU-only is explicitly unsupported.

### Tier 1 — Pilot / POC (≤ 5 concurrent calls)
| Resource | Minimum |
|---|---|
| GPU | 1× NVIDIA **L4** or **A10** or **RTX 4090** — **24 GB VRAM** |
| CPU | 8 vCPU |
| RAM | 32 GB |
| Disk | 100 GB NVMe SSD |
| Network | 50 Mbps up/down, stable; egress to carrier allowed |
| VRAM budget | LLM 8B FP8 ~9 GB + Whisper turbo ~3 GB + Kokoro ~2 GB ≈ 14 GB (fits 24 GB with headroom) |

### Tier 2 — Production (~25 concurrent calls)
| Resource | Recommended |
|---|---|
| GPU | 1× **A100 40 GB** or 2× **L4 24 GB** |
| CPU | 16 vCPU |
| RAM | 64 GB |
| Disk | 250 GB NVMe |
| Network | 200 Mbps, low jitter |
| Notes | vLLM batches LLM across calls efficiently; STT is the per-stream cost |

### Tier 3 — Scale (100+ concurrent)
| Resource | Recommended |
|---|---|
| GPU | Multiple **A100 80 GB / H100**, or a GPU pool |
| Architecture | Split services: dedicated LLM node(s) (vLLM), STT node(s), TTS node(s); scale horizontally behind the orchestrator |
| CPU/RAM | 32+ vCPU, 128+ GB per node |
| Network | 1 Gbps+ |

**Concurrency rule of thumb (single 24 GB GPU):** ~5–10 simultaneous calls before STT/TTS contention degrades latency. LLM is rarely the bottleneck thanks to batching; STT (one stream per call) usually is. Benchmark on real hardware before quoting numbers to customers.

---

## 7. Networking & firewall

| Direction | Endpoint | Purpose | Required |
|---|---|---|---|
| Outbound | Carrier (Twilio media + REST) | Call audio + call control | Yes |
| Inbound | Carrier → telephony-bridge WS | Media Streams (if inbound calls) | If inbound |
| Outbound | Control-plane cloud (HTTPS) | Config pull + usage metering | Yes (or air-gap mode) |
| Internal | loopback / docker network | Service-to-service | Yes |

- Air-gapped customers: provide **offline license file + manual config import**; disable control-plane callout.
- All internal inference traffic stays on the Docker bridge network — never exposed.

---

## 8. Security & compliance posture

- **At rest:** Postgres + MinIO encryption (LUKS or app-level); recordings off by default, opt-in per agent.
- **In transit:** TLS for control-plane; WSS for Twilio; mTLS optional between services.
- **Secrets:** carrier creds + model licenses via Docker secrets / env injection, never baked into images.
- **License/metering:** report **minutes only**, never call content. Offline-license mode for air-gapped.
- **Customer owns telecom compliance** (10DLC, TCPA consent, AI disclosure) under their own carrier account — document this clearly in onboarding.

---

## 9. Bill of materials (Tier 1 reference deployment)

```yaml
# docker-compose.yml (sketch — services, not full config)
services:
  telephony-bridge:   # Node/Python, Twilio Media Streams WS
  orchestrator:       # Pipecat pipeline (VAD, turn-taking, barge-in)
  stt:                # faster-whisper large-v3-turbo (GPU)
  llm:                # vLLM serving Llama-3.1-8B-Instruct FP8 (GPU)
  tts:                # Kokoro-82M streaming (GPU)
  postgres:           # config + transcripts
  redis:              # live call state
  minio:              # recordings (optional, off by default)
  prometheus:         # metrics
  grafana:            # dashboards
  agent-sidecar:      # config pull + usage metering / license
# All GPU services request: deploy.resources.reservations.devices (nvidia)
```

---

## 10. Open decisions to lock before build

1. **Orchestration:** adopt **Pipecat** as the foundation (recommended — saves months) vs. build custom. Pipecat gets you Twilio + local model wiring + interruption handling out of the box.
2. **STT quality vs. cost:** open faster-whisper vs. Deepgram on-prem (paid, lower latency). Start open; offer Deepgram as a premium tier.
3. **TTS naturalness vs. speed:** Kokoro (balanced) vs. Orpheus (more natural, heavier) vs. Piper (fastest). Make it configurable per agent.
4. **Model distribution:** bake models into the image (huge images, simple) vs. download on first boot (smaller image, needs egress or a local mirror for air-gap).
5. **Carrier abstraction:** Twilio-only first, design the bridge interface so SIP can be added later.

---

## 10b. Development environment (constrained hardware)

> Reality of current dev hardware: max GPU is an **RTX 4050 mobile (6 GB VRAM)** on a Ryzen 7 laptop; primary machine is an **i5 with no GPU**. This is enough to **build and prove the pipeline**, but NOT to judge production latency (6 GB forces smaller models, and laptop GPUs thermal-throttle under sustained call load).

**Principle: decouple app dev from GPU.** vLLM, Ollama, and OpenAI all speak the OpenAI-compatible API — write the app against that interface and swap backends freely (cloud today, local tomorrow, no code change).

### 6 GB dev config (fits with headroom ~3.2 GB on GPU)
| Layer | Production (24 GB) | 6 GB dev config | VRAM |
|---|---|---|---|
| LLM runtime | vLLM | **Ollama** (GGUF, Windows-friendly, OpenAI-compatible) | — |
| LLM model | Llama-3.1-8B | **Qwen2.5-3B-Instruct** Q4 (or Llama-3.2-3B) | ~2.3 GB |
| STT | whisper large-v3-turbo | **faster-whisper `small`** int8 | ~0.5 GB |
| TTS | Kokoro / Orpheus | **Kokoro-82M** (or Piper on CPU) | ~0.4 GB |

- Use **Ollama, not vLLM**, on the laptop (vLLM is painful on 6 GB/Windows).
- Optional: run STT/TTS on the Ryzen CPU to free VRAM for a 7B Q4 LLM on GPU (costs latency).

### Hardware allocation
1. **i5 (no GPU):** web designer, control plane, telephony bridge, orchestrator code. Point model calls at a cloud API or the colleague's GPU laptop over LAN during dev.
2. **RTX 4050 6 GB:** run the real local-inference path (Ollama + faster-whisper + Kokoro) to test barge-in and end-to-end plumbing.
3. **Rented cloud GPU (~$0.30–0.70/hr, RunPod/Vast/Lambda; RTX 4090 or L4 24 GB):** use for the latency-validation milestone and customer demos. A few dollars total — no need to own production hardware.

## 11. Recommended first milestone (validate the riskiest assumption)

Build a **single-call vertical slice** on Tier-1 hardware:

> Outbound call via Twilio Media Streams → faster-whisper → vLLM (Llama 3.1 8B) → Kokoro → back to caller, with barge-in working.

Measure real end-of-speech→bot latency on the target GPU. If you can't get under ~900 ms with clean interruptions, fix that **before** building the web designer or control plane — everything else depends on it.
```
