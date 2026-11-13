"""
Voice Agent Studio — Speech Service Engine.
Handles local Faster-Whisper (CUDA) Speech-to-Text inference,
Silero VAD, hallucination filtering, and Text-to-Speech (SAPI5 / pyttsx3 / Edge-TTS).
"""

import os
import io
import re
import asyncio
from collections import OrderedDict
from typing import Optional, List, Dict, Any

WHISPER_HALLUCINATIONS = {
    "thanks for watching", "subtitles by", "subtitles by the amara org community",
    "subtitles by the amara.org community", "music", "please subscribe",
    "subscribe", "like and subscribe", "watching"
}

STUDIO_VOICES = [
    {"id": "zira", "name": "Microsoft Zira (Windows Native Offline - Female)"},
    {"id": "david", "name": "Microsoft David (Windows Native Offline - Male)"},
    {"id": "en-US-AriaNeural", "name": "Aria (Edge Neural - Online Female)"},
    {"id": "en-US-GuyNeural", "name": "Guy (Edge Neural - Online Male)"},
    {"id": "en-US-JennyNeural", "name": "Jenny (Edge Neural - Online Female)"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (Edge Neural - Online UK Female)"},
    {"id": "en-IN-NeerjaNeural", "name": "Neerja (Edge Neural - Online India Female)"},
    {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Edge Neural - Online India Male)"},
]

def _clean_whisper_text(text: str) -> str:
    """Strip all non-word punctuation before checking against hallucination set."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


_CACHED_LOCAL_WHISPER = None

def get_local_whisper():
    """Thread-safe singleton for Faster-Whisper with GPU acceleration and warm-up."""
    global _CACHED_LOCAL_WHISPER
    if _CACHED_LOCAL_WHISPER is not None:
        return _CACHED_LOCAL_WHISPER
    try:
        from faster_whisper import WhisperModel
        import ctranslate2
        try:
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False
        device = "cuda" if has_cuda else "cpu"
        compute_type = "float16" if has_cuda else "int8"
        print(f"[STT] Initializing Local Faster-Whisper on {device.upper()} ({compute_type})...")
        model = WhisperModel("base.en", device=device, compute_type=compute_type)
        # Pre-warm CUDA graph with 0.1s dummy audio so first voice turn has zero cold start lag
        try:
            import wave
            wio = io.BytesIO()
            with wave.open(wio, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 1600)
            wio.seek(0)
            list(model.transcribe(wio, vad_filter=True)[0])
            print("[STT] Local Faster-Whisper CUDA warm-up complete!")
        except Exception as we:
            print(f"[STT] Warm-up notice: {we}")
        _CACHED_LOCAL_WHISPER = model
        return _CACHED_LOCAL_WHISPER
    except Exception as e:
        print(f"[STT] Local Faster-Whisper init failed: {e}")
        return None


# LRU-limited OrderedDict (max 256 entries = ~25MB RAM)
_TTS_CACHE: OrderedDict = OrderedDict()
_TTS_CACHE_MAX = 256

def _tts_cache_put(key: str, value: tuple):
    if key in _TTS_CACHE:
        _TTS_CACHE.move_to_end(key)
    else:
        if len(_TTS_CACHE) >= _TTS_CACHE_MAX:
            _TTS_CACHE.popitem(last=False)
        _TTS_CACHE[key] = value

def _tts_cache_get(key: str):
    if key not in _TTS_CACHE:
        return None
    _TTS_CACHE.move_to_end(key)
    return _TTS_CACHE[key]


def _apply_sapi5_voice(engine, requested_voice: str, rate: float = 1.0):
    v_list = engine.getProperty("voices") or []
    req = (requested_voice or "").lower().strip()
    is_male = any(m in req for m in ["david", "male", "guy", "christopher", "george"])
    selected_id = None

    if is_male:
        for v in v_list:
            if "david" in v.name.lower() or "male" in v.name.lower():
                selected_id = v.id
                break
    else:
        for v in v_list:
            if "zira" in v.name.lower() or "female" in v.name.lower():
                selected_id = v.id
                break

    if not selected_id and v_list:
        for v in v_list:
            if not is_male and ("zira" in v.id.lower() or "female" in v.id.lower()):
                selected_id = v.id
                break
        if not selected_id:
            if not is_male and len(v_list) > 1:
                selected_id = v_list[1].id
            else:
                selected_id = v_list[0].id

    if selected_id:
        engine.setProperty("voice", selected_id)
    engine.setProperty("rate", int(200 * rate))


async def synthesize_speech_bytes(text: str, voice: str = "zira", rate: float = 1.0) -> bytes:
    """Synthesize speech returning WAV bytes (used by Twilio telephony and TTS caching)."""
    if not text:
        return b""
    clean_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    clean_text = re.sub(r"\*([^*]+)\*", r"\1", clean_text)
    clean_text = re.sub(r"[#*`_~]", "", clean_text).strip()

    cache_key = f"{voice}_{rate}_{clean_text}"
    cached = _tts_cache_get(cache_key)
    if cached and cached[1] == "audio/wav":
        return cached[0]

    def _sync_pyttsx3():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import pyttsx3, tempfile
        try:
            engine = pyttsx3.init()
            _apply_sapi5_voice(engine, voice, rate)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            engine.save_to_file(clean_text, tmp_path)
            engine.runAndWait()
            with open(tmp_path, "rb") as f:
                wav_bytes = f.read()
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return wav_bytes
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    try:
        wav_bytes = await asyncio.to_thread(_sync_pyttsx3)
        if wav_bytes:
            _tts_cache_put(cache_key, (wav_bytes, "audio/wav"))
            return wav_bytes
    except Exception as e:
        print(f"[synthesize_speech_bytes] error: {e}")
    return b""


async def transcribe_audio_bytes(
    raw_bytes: bytes,
    language: Optional[str] = None,
    prompt: Optional[str] = None,
    stt_api_key: Optional[str] = None,
    stt_base_url: Optional[str] = None,
    stt_model: Optional[str] = None
) -> str:
    """Transcribe raw audio bytes using local Faster-Whisper or cloud STT fallback."""
    if not raw_bytes or len(raw_bytes) < 1024:
        return ""
    target_lang = (language or "en").split("-")[0].lower()
    default_prompt = (prompt or "Conversational English voice call: appointments, phone numbers, digits 0-9, mobile numbers, bookings, schedule, names, dates.").strip()

    model = get_local_whisper()
    if model:
        def _sync_transcribe(raw: bytes) -> str:
            segments, _ = model.transcribe(
                io.BytesIO(raw),
                beam_size=5,
                language=target_lang,
                initial_prompt=default_prompt,
                temperature=0.0,
                condition_on_previous_text=False,
                repetition_penalty=1.2,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=450)
            )
            raw_text = " ".join([seg.text for seg in segments]).strip()
            parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", raw_text) if p.strip()]
            deduped = []
            for p in parts:
                if not deduped or deduped[-1].lower() != p.lower():
                    deduped.append(p)
            return " ".join(deduped) if deduped else raw_text
        try:
            text = await asyncio.to_thread(_sync_transcribe, raw_bytes)
            if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                text = ""
            return text
        except Exception as e:
            print(f"[transcribe_audio_bytes] Local faster-whisper error: {e}")

    if stt_api_key and stt_api_key != "ollama" and stt_base_url and "groq" in stt_base_url:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                files = {"file": ("utterance.wav", raw_bytes, "audio/wav")}
                data = {
                    "model": stt_model or "whisper-large-v3-turbo",
                    "temperature": "0.0",
                    "language": target_lang,
                    "prompt": default_prompt,
                    "response_format": "json"
                }
                headers = {"Authorization": f"Bearer {stt_api_key}"}
                r = await client.post(f"{stt_base_url}/audio/transcriptions", files=files, data=data, headers=headers)
                if r.status_code == 200:
                    text = (r.json().get("text") or "").strip()
                    if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                        text = ""
                    return text
        except Exception as e:
            print(f"[transcribe_audio_bytes] Cloud STT error: {e}")

    return ""
