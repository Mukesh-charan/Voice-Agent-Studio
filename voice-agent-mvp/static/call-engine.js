"use strict";

/**
 * LocalWhisperSTT — Industrial Hysteresis VAD with Zero-Cutoff Architecture:
 * - Dual-threshold Hysteresis:
 *     startThreshold = adaptive (noiseFloor * 1.8, min 0.018)
 *     continueThreshold = adaptive (noiseFloor * 1.2, min 0.010)
 * - Anti-cutoff Silence Window: 0.45s sustained silence before finalizing.
 * - Noise Floor Shield: sampled only when idle, never drifts while speaking.
 * - 16kHz resampling for Groq Whisper / local Faster-Whisper
 */
class LocalWhisperSTT {
  constructor({ onFinal, onBargeIn, onStatus, getState, lang }) {
    this.onFinal = onFinal || (() => {});
    this.onBargeIn = onBargeIn || null;
    this.onStatus = onStatus || (() => {});
    this.getState = getState || (() => "listening");
    this.lang = lang || "en-US";
    this.audioContext = null;
    this.mediaStream = null;
    this.processor = null;
    this.source = null;
    this.active = false;
    this.isRecording = false;
    this.audioBuffer = [];
    this.preRollRing = [];
    this.silenceSamples = 0;
    this.noiseFloor = 0.012;
    this.isDeaf = false;
    this._deafTimer = null;
    this.isTranscribing = false;
    this.speakerBleedRms = 0.015;
    this._bargeInHits = 0;
  }

  setListening() {
    if (this._deafTimer) clearTimeout(this._deafTimer);
    this.isDeaf = false;
    if (this.getState() === "listening") {
      this.onStatus("Listening\u2026", "listening");
    }
  }

  setDeaf() {
    if (this._deafTimer) clearTimeout(this._deafTimer);
    this.isDeaf = true;
    this.isRecording = false;
    this.audioBuffer = [];
    this.silenceSamples = 0;
  }

  async start() {
    try {
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      this.audioContext = new AudioCtx();
      if (this.audioContext.state === "suspended") {
        await this.audioContext.resume();
      }

      this.source = this.audioContext.createMediaStreamSource(this.mediaStream);
      this.active = true;

      const sampleRate = this.audioContext.sampleRate;
      const silenceSampleLimit = Math.floor(sampleRate * 0.70); // 700ms natural conversational pause
      const minUtteranceSamples = Math.floor(sampleRate * 0.35); // 350ms minimum speech
      const maxUtteranceSamples = Math.floor(sampleRate * 12.0); // 12s maximum utterance

      const handleAudioChunk = (inputData) => {
        if (!this.active || this.isDeaf) return;
        const state = this.getState();

        let sum = 0;
        for (let i = 0; i < inputData.length; i++) {
          sum += inputData[i] * inputData[i];
        }
        const rms = Math.sqrt(sum / inputData.length);

        // 1. If AGENT IS SPEAKING:
        // Do NOT record speaker audio into the user speech buffer!
        // Instead, monitor for legitimate user BARGE-IN:
        if (state === "speaking") {
          // Grace period: First 600ms after speech begins, reject barge-in to avoid tripping on initial speaker transient
          const timeSinceSpeak = Date.now() - (this.speakStartedAt || 0);
          if (timeSinceSpeak < 600) {
            this._bargeInHits = 0;
            return;
          }

          this.speakerBleedRms = Math.max(0.012, (this.speakerBleedRms || 0.015) * 0.95 + rms * 0.05);
          // Human barge-in must be significantly louder than speaker bleed
          const bargeInThreshold = Math.max(0.060, this.speakerBleedRms * 2.2);

          if (rms > bargeInThreshold) {
            this._bargeInHits = (this._bargeInHits || 0) + 1;
            // Require sustained speech (at least 5 blocks = ~215ms)
            if (this._bargeInHits >= 5) {
              console.log(`🗣️ [BARGE-IN] Detected sustained user voice (RMS ${rms.toFixed(4)})`);
              this._bargeInHits = 0;
              if (this.onBargeIn) {
                this.onBargeIn(inputData);
              }
            }
          } else {
            this._bargeInHits = Math.max(0, (this._bargeInHits || 0) - 1);
          }
          // Never let speaker audio accumulate into recording buffer!
          return;
        }

        // Only listen and record when state is strictly "listening"
        if (state !== "listening") {
          this._bargeInHits = 0;
          this.isRecording = false;
          this.audioBuffer = [];
          return;
        }

        this._bargeInHits = 0;
        this.speakerBleedRms = 0.015;

        // 2. If AGENT IS THINKING OR LISTENING:
        if (!this.isRecording) {
          this.noiseFloor = Math.min(0.025, Math.max(0.005, this.noiseFloor * 0.96 + rms * 0.04));
          const startThreshold = Math.max(0.015, this.noiseFloor * 1.8);

          this.preRollRing.push(new Float32Array(inputData));
          if (this.preRollRing.length > 5) this.preRollRing.shift();

          if (rms > startThreshold) {
            this.isRecording = true;
            this.audioBuffer = [...this.preRollRing, new Float32Array(inputData)];
            this.preRollRing = [];
            this.silenceSamples = 0;
            this.onStatus("Listening\u2026", "listening");
          }
        } else {
          const continueThreshold = Math.max(0.009, this.noiseFloor * 1.2);
          this.audioBuffer.push(new Float32Array(inputData));

          if (rms > continueThreshold) {
            this.silenceSamples = 0;
          } else {
            this.silenceSamples += inputData.length;
          }

          const totalSamples = this.audioBuffer.reduce((acc, b) => acc + b.length, 0);

          if (this.silenceSamples >= silenceSampleLimit || totalSamples >= maxUtteranceSamples) {
            this.isRecording = false;
            this.silenceSamples = 0;

            if (totalSamples >= minUtteranceSamples) {
              const merged = new Float32Array(totalSamples);
              let offset = 0;
              for (const b of this.audioBuffer) {
                merged.set(b, offset);
                offset += b.length;
              }
              this.audioBuffer = [];
              const resampled = this._downsampleTo16k(merged, sampleRate);
              const wavBlob = this._encodeWav(resampled, 16000);
              this._sendToWhisper(wavBlob);
            } else {
              this.audioBuffer = [];
              if (this.getState() === "listening") {
                this.onStatus("Listening\u2026", "listening");
              }
            }
          }
        }
      };

      // Bug 2 Fix: Prefer AudioWorkletNode (vad-processor.js) over deprecated ScriptProcessor
      if (this.audioContext.audioWorklet && window.AudioWorkletNode) {
        try {
          await this.audioContext.audioWorklet.addModule("/vad-processor.js");
          this.workletNode = new AudioWorkletNode(this.audioContext, "vad-processor");
          this.workletNode.port.onmessage = (event) => {
            if (event.data && event.data.type === "audio" && event.data.chunk) {
              handleAudioChunk(event.data.chunk);
            }
          };
          this.source.connect(this.workletNode);
        } catch (workletErr) {
          console.warn("AudioWorklet fallback to ScriptProcessor:", workletErr);
          this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
          this.processor.onaudioprocess = (e) => handleAudioChunk(e.inputBuffer.getChannelData(0));
          this.source.connect(this.processor);
          this.silentGain = this.audioContext.createGain();
          this.silentGain.gain.value = 0;
          this.processor.connect(this.silentGain);
          this.silentGain.connect(this.audioContext.destination);
        }
      } else {
        this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
        this.processor.onaudioprocess = (e) => handleAudioChunk(e.inputBuffer.getChannelData(0));
        this.source.connect(this.processor);
        this.silentGain = this.audioContext.createGain();
        this.silentGain.gain.value = 0;
        this.processor.connect(this.silentGain);
        this.silentGain.connect(this.audioContext.destination);
      }

      this.onStatus("Listening\u2026", "listening");
    } catch (err) {
      console.error("LocalWhisperSTT startup failed:", err);
      this.onStatus("Mic Error: " + err.message, "error");
      throw err;
    }
  }

  _downsampleTo16k(input, sourceRate) {
    if (sourceRate === 16000) return input;
    const ratio = sourceRate / 16000;
    const newLen = Math.round(input.length / ratio);
    const out = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) {
      const origIdx = i * ratio;
      const left = Math.floor(origIdx);
      const right = Math.min(left + 1, input.length - 1);
      const w = origIdx - left;
      out[i] = input[left] * (1 - w) + input[right] * w;
    }
    return out;
  }

  _encodeWav(samples, sampleRate) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };
    writeString(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeString(8, "WAVE");
    writeString(12, "fmt ");
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true);
    view.setUint16(32, 2, true);
    view.setUint16(34, 16, true);
    writeString(36, "data");
    view.setUint32(40, samples.length * 2, true);
    let offset = 44;
    for (let i = 0; i < samples.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Blob([view], { type: "audio/wav" });
  }

  async _sendToWhisper(wavBlob) {
    if (this.isTranscribing) return;
    this.isTranscribing = true;
    try {
      this.onStatus("Transcribing (Local Faster-Whisper)\u2026", "thinking");
      const formData = new FormData();
      formData.append("file", wavBlob, "utterance.wav");
      if (this.lang) formData.append("language", this.lang);
      formData.append("prompt", "Conversational English voice call: appointments, bookings, schedule, names.");

      const res = await fetch("/api/transcribe", { method: "POST", body: formData });
      if (!res.ok) throw new Error("STT HTTP " + res.status);
      const data = await res.json();
      const text = (data.text || "").trim();

      if (text) {
        this.onFinal(text);
      } else {
        if (this.getState() === "listening") {
          this.onStatus("Listening\u2026", "listening");
        }
      }
    } catch (err) {
      console.warn("Whisper transcription error:", err);
      if (this.getState() === "listening") {
        this.onStatus("Listening\u2026", "listening");
      }
    } finally {
      this.isTranscribing = false;
    }
  }

  stop() {
    this.active = false;
    this.setDeaf();
    if (this.workletNode) {
      try { this.workletNode.disconnect(); this.workletNode.port.close(); } catch (e) {}
      this.workletNode = null;
    }
    if (this.processor) { try { this.processor.disconnect(); } catch (e) {} this.processor = null; }
    if (this.silentGain) { try { this.silentGain.disconnect(); } catch (e) {} this.silentGain = null; }
    if (this.source) { try { this.source.disconnect(); } catch (e) {} this.source = null; }
    if (this.mediaStream) { this.mediaStream.getTracks().forEach((t) => t.stop()); this.mediaStream = null; }
    if (this.audioContext && this.audioContext.state !== "closed") {
      try { this.audioContext.close(); } catch (e) {}
      this.audioContext = null;
    }
  }
}

/**
 * CallEngine — Production voice conversation pipeline
 * - Gapless Audio Prefetching TTS (low inter-sentence latency)
 * - SSE Streaming LLM (first audio starts before LLM finishes)
 * - Hard-gated echo prevention (no self-transcription loop)
 * - Zero-Cutoff Hysteresis VAD via LocalWhisperSTT
 * - Fail-safe thinking watchdog (auto-recovers from network hangs)
 */
class CallEngine {
  constructor({ onStatus, onTurn, onTurnUpdate, onEvent } = {}) {
    this.onStatus = onStatus || (() => {});
    this.onTurn = onTurn || (() => {});
    this.onTurnUpdate = onTurnUpdate || (() => {});
    this.onEvent = onEvent || (() => {});
    this.SR = null; // Cloud WebSpeech disabled completely to eliminate acoustic self-echo
    this.synth = window.speechSynthesis;

    this.active = false;
    this.state = "idle";
    this.messages = [];
    this.transcript = [];
    this.recognition = null;
    this.localSTT = null;
    this.config = null;
    this.speakGen = 0;
    this.streamGen = 0;
    this.currentStreamController = null;
    this.audioPlayer = new Audio();
    this.currentAudio = null;
    this.audioPreloadCache = new Map();
    this.lastSpokenText = "";
    this.lastSpokenAt = 0;
    this.speechEndedAt = 0;
    this.spokenPhrases = [];
    this._thinkingTimeout = null;
    this.speakQueue = [];
    this.isSpeakingQueue = false;
    this.streamCompleted = false;
    this.speakOnDone = null;
  }

  supported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia) || !!this.SR;
  }

  _unlockAudio() {
    try {
      if (!this.audioPlayer) this.audioPlayer = new Audio();
      this.audioPlayer.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
      const p = this.audioPlayer.play();
      if (p && p.catch) p.catch(() => {});
    } catch (e) {}
    if (this.synth) {
      try {
        this.synth.cancel();
        this.synth.resume();
        const dummy = new SpeechSynthesisUtterance(" ");
        dummy.volume = 0.01;
        this.synth.speak(dummy);
      } catch (e) {}
    }
  }

  start(config) {
    this.config = config || {};
    this.active = true;
    this.messages = [];
    this.transcript = [];
    this._unlockAudio();

    if (this.localSTT) { this.localSTT.stop(); this.localSTT = null; }
    if (this.recognition) { try { this.recognition.abort(); } catch (e) {} this.recognition = null; }

    // Sole STT engine: Local Faster-Whisper on CUDA with AudioWorklet Hysteresis VAD
    this._startLocalSTT();
    if (this.localSTT) {
      this.localSTT.isDeaf = false; // ensure listening is enabled
    }

    const greeting = this._cleanSpeech((config.greeting || "").trim());
    if (greeting) {
      this._registerSpokenText(greeting);
      this._addTurn("agent", greeting);
      this.messages.push({ role: "assistant", content: greeting });
      this.state = "speaking";
      this.lastSpokenText = greeting;
      this.lastSpokenAt = Date.now();
      this.onStatus("Speaking\u2026", "speaking");
      this._speak(greeting, () => this._toListening());
    } else {
      this._toListening();
    }
  }

  _startLocalSTT() {
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      this.localSTT = new LocalWhisperSTT({
        onFinal: (text) => this._onFinal(text),
        onBargeIn: (chunk) => this._onBargeIn(chunk),
        onStatus: (text, cls) => {
          if (this.state === "listening" || this.state === "idle") {
            this.onStatus(text, cls);
          }
        },
        getState: () => this.state,
        lang: (this.config && this.config.lang) || "en-US",
      });
      this.localSTT.start().catch((err) => {
        console.error("Local Whisper STT startup failed:", err);
        this.onStatus("Mic error: " + err.message, "error");
      });
    } else {
      this.onStatus("Mic not supported in this browser", "error");
    }
  }

  _onBargeIn(chunk) {
    if (!this.active) return;
    if (this.config && this.config.bargeIn === 0) return;

    console.log("⚡ [BARGE-IN] Interrupted agent speech by user voice!");
    this._cancelSpeech();
    this.state = "listening";
    this.onStatus("Listening\u2026", "listening");

    if (this.localSTT) {
      this.localSTT.isRecording = true;
      // Start user recording with clean buffer (do NOT preload speaker chunk)
      this.localSTT.audioBuffer = [];
      this.localSTT.silenceSamples = 0;
      this.localSTT.isDeaf = false;
    }
  }

  hangUp() {
    this.active = false;
    this.state = "idle";
    this._cancelSpeech();
    if (this._thinkingTimeout) { clearTimeout(this._thinkingTimeout); this._thinkingTimeout = null; }
    if (this.localSTT) { this.localSTT.stop(); this.localSTT = null; }
    try { this.recognition && this.recognition.stop(); } catch (e) {}
    this.onStatus("Call ended", "");
  }

  _addTurn(role, text) {
    this.transcript.push({ role, text });
    this.onTurn(role, text);
  }

  _updateLastTurn(text) {
    if (this.transcript.length > 0) {
      this.transcript[this.transcript.length - 1].text = text;
    }
    this.onTurnUpdate(text);
  }

  _toListening() {
    if (!this.active) return;
    if (this._thinkingTimeout) { clearTimeout(this._thinkingTimeout); this._thinkingTimeout = null; }
    this.speechEndedAt = Date.now();
    this.state = "listening";
    this.onStatus("Listening\u2026", "listening");

    if (this.localSTT) {
      this.localSTT.lastSpokenAt = Date.now();
      this.localSTT.isRecording = false;
      this.localSTT.audioBuffer = [];
      this.localSTT.silenceSamples = 0;
      // Deafness cooldown guard: mute mic for 450ms while room reverberation and speaker echo die down
      this.localSTT.setDeaf();
      if (this._cooldownTimer) clearTimeout(this._cooldownTimer);
      this._cooldownTimer = setTimeout(() => {
        if (this.active && this.state === "listening" && this.localSTT) {
          this.localSTT.isDeaf = false;
          this.localSTT.isRecording = false;
          this.localSTT.audioBuffer = [];
          this.localSTT.silenceSamples = 0;
        }
      }, 450);
    }
  }

  _registerSpokenText(text) {
    if (!text) return;
    const clean = text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").trim();
    if (!clean) return;
    this.lastSpokenText = clean;
    this.lastSpokenAt = Date.now();
    if (!this.spokenPhrases) this.spokenPhrases = [];
    this.spokenPhrases.push({ text: clean, time: Date.now() });
    const cutoff = Date.now() - 30000;
    this.spokenPhrases = this.spokenPhrases.filter((p) => p.time > cutoff);
  }

  _isEchoOfRecentSpeech(text) {
    if (!text) return false;
    const cleanText = text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").trim();
    if (!cleanText) return false;

    const userWords = cleanText.split(/\s+/).filter((w) => w.length > 2);
    if (!userWords.length) return false;

    const phrases = (this.spokenPhrases || []).map((p) => p.text);
    if (this.lastSpokenText && !phrases.includes(this.lastSpokenText)) {
      phrases.push(this.lastSpokenText);
    }

    for (const phrase of phrases) {
      if (!phrase) continue;
      // 1. Exact or bidirectional substring match
      if (phrase === cleanText || phrase.includes(cleanText) || cleanText.includes(phrase)) {
        console.log(`🛡️ [ECHO SHIELD] Substring echo suppressed: "${cleanText}"`);
        return true;
      }

      // 2. Token overlap / Jaccard similarity:
      // If 50% or more of the words transcribed by Whisper match words in the agent's recent speech
      const phraseWords = new Set(phrase.split(/\s+/));
      let matches = 0;
      for (const w of userWords) {
        if (phraseWords.has(w)) matches++;
      }
      const overlap = matches / userWords.length;
      if (overlap >= 0.5) {
        console.log(`🛡️ [ECHO SHIELD] Word overlap echo suppressed (${Math.round(overlap * 100)}%): "${cleanText}"`);
        return true;
      }
    }

    return false;
  }

  _voiceByName(name) {
    if (!this.synth) return null;
    const vs = this.synth.getVoices() || [];
    if (!vs.length) return null;
    const isMale = name && /david|male|guy|george/i.test(name);
    if (!name) {
      const female = vs.find((v) => /zira|aria|jenny|female|samantha|victoria/i.test(v.name));
      if (female) return female;
      return vs.find((v) => v.lang && v.lang.toLowerCase().startsWith("en")) || vs[0];
    }
    const n = name.toLowerCase();
    let match = vs.find((v) => v.name === name || v.voiceURI === name);
    if (match) return match;
    if (n.includes("zira")) match = vs.find((v) => v.name.toLowerCase().includes("zira"));
    else if (n.includes("david")) match = vs.find((v) => v.name.toLowerCase().includes("david"));
    else if (n.includes("aria") || n.includes("natural")) match = vs.find((v) => v.name.toLowerCase().includes("aria") || v.name.toLowerCase().includes("natural"));
    else if (n.includes("jenny")) match = vs.find((v) => v.name.toLowerCase().includes("jenny"));
    if (match) return match;
    match = vs.find((v) => v.name.toLowerCase().includes(n));
    if (match) return match;
    const lang = (this.config && this.config.lang) ? this.config.lang.toLowerCase() : "en";
    match = vs.find((v) => v.lang && v.lang.toLowerCase().startsWith(lang.slice(0, 2)));
    if (match) return match;
    if (!isMale) {
      const female = vs.find((v) => /zira|aria|jenny|female|samantha|victoria/i.test(v.name));
      if (female) return female;
    }
    return vs.find((v) => v.lang && v.lang.toLowerCase().startsWith("en")) || vs[0];
  }

  _cleanSpeech(text) {
    if (!text) return "";
    return text
      .replace(/\{"name":\s*"[^"]*",\s*"(?:parameters|arguments)":\s*\{[^}]*\}\}/gi, "")
      .replace(/\{[^{}]*"(?:name|function|parameters|arguments)"[^{}]*\}/gi, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/\*+/g, "")
      .replace(/^#+\s*/gm, "")
      .replace(/^\s*[-\u2022]\s*/gm, "")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/`+([^`]+)`+/g, "$1")
      .replace(/\s+/g, " ")
      .trim();
  }

  _splitSentences(text) {
    if (!text) return [];
    let s = this._cleanSpeech(text);
    s = s.replace(/(\d+)\.(\d+)/g, "$1___DEC___$2");
    const abbrevs = ["a.m.", "p.m.", "am", "pm", "dr.", "mr.", "mrs.", "ms.", "rs.", "e.g.", "i.e.", "vs."];
    abbrevs.forEach((ab, idx) => {
      const reg = new RegExp("\\b" + ab.replace(".", "\\."), "gi");
      s = s.replace(reg, `___AB${idx}___`);
    });
    const matches = s.match(/[^.!?\n]+[.!?\n]+/g) || [s];
    return matches.map((part) => {
      let restored = part;
      abbrevs.forEach((ab, idx) => {
        restored = restored.replace(new RegExp(`___AB${idx}___`, "g"), ab);
      });
      restored = restored.replace(/___DEC___/g, ".");
      return this._cleanSpeech(restored);
    }).filter((p) => p.length > 0);
  }

  _cancelSpeech() {
    this.speakGen++;
    this.streamGen++;
    this.speakQueue = [];
    this.isSpeakingQueue = false;
    this.streamCompleted = false;
    this.speakOnDone = null;

    if (this.currentAudio) {
      try { this.currentAudio.pause(); this.currentAudio.currentTime = 0; this.currentAudio.src = ""; } catch (e) {}
      this.currentAudio = null;
    }
    if (this.audioPlayer) {
      try { this.audioPlayer.pause(); this.audioPlayer.currentTime = 0; } catch (e) {}
    }
    if (this.audioPreloadCache) {
      for (const [_, p] of this.audioPreloadCache.entries()) {
        p.then((res) => { if (res && res.url) URL.revokeObjectURL(res.url); }).catch(() => {});
      }
      this.audioPreloadCache.clear();
    }
    if (this.currentStreamController) {
      try { this.currentStreamController.abort(); } catch (e) {}
      this.currentStreamController = null;
    }
    if (this.synth) { try { this.synth.cancel(); } catch (e) {} }
    if (window._activeUtterance) {
      window._activeUtterance.onend = null;
      window._activeUtterance.onerror = null;
      window._activeUtterance = null;
    }
    if (this.active && this.state === "speaking") {
      this.state = "listening";
      this.onStatus("Listening\u2026", "listening");
    }
  }

  _resetAudioQueue() {
    this.speakGen++;
    this.speakQueue = [];
    this.isSpeakingQueue = false;
    this.streamCompleted = false;
    this.speakOnDone = null;
    if (this.currentAudio) {
      try { this.currentAudio.pause(); this.currentAudio.currentTime = 0; this.currentAudio.src = ""; } catch (e) {}
      this.currentAudio = null;
    }
    if (this.audioPreloadCache) {
      for (const [_, p] of this.audioPreloadCache.entries()) {
        p.then((res) => { if (res && res.url) URL.revokeObjectURL(res.url); }).catch(() => {});
      }
      this.audioPreloadCache.clear();
    }
    if (this.synth) { try { this.synth.cancel(); } catch (e) {} }
    if (window._activeUtterance) {
      window._activeUtterance.onend = null;
      window._activeUtterance.onerror = null;
      window._activeUtterance = null;
    }
  }

  _startSpeaking(onDone) {
    this._resetAudioQueue();
    this.active = true;
    this.state = "speaking";
    if (this.localSTT) {
      this.localSTT.speakStartedAt = Date.now();
      this.localSTT.isRecording = false;
      this.localSTT.audioBuffer = [];
      this.localSTT.silenceSamples = 0;
      this.localSTT._bargeInHits = 0;
    }
    this.speakOnDone = onDone || (() => this._toListening());
  }

  _prefetchAudio(sentence) {
    sentence = this._cleanSpeech(sentence);
    if (!sentence) return null;
    if (this.audioPreloadCache.has(sentence)) return this.audioPreloadCache.get(sentence);
    const gen = this.speakGen;
    const fetchPromise = (async () => {
      try {
        const res = await fetch("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text: sentence,
            voice: (this.config && this.config.voiceName) || "en-US-AriaNeural",
            rate: (this.config && this.config.rate) || 1.0,
          }),
        });
        if (!res.ok) throw new Error("TTS status " + res.status);
        const blob = await res.blob();
        if (gen !== this.speakGen || !this.active) return null;
        const url = URL.createObjectURL(blob);
        return { url };
      } catch (err) {
        return null;
      }
    })();
    this.audioPreloadCache.set(sentence, fetchPromise);
    return fetchPromise;
  }

  _enqueueSentence(sentence) {
    sentence = this._cleanSpeech(sentence);
    if (!sentence) return;
    this._registerSpokenText(sentence);
    this.speakQueue.push(sentence);
    this._prefetchAudio(sentence);
    if (!this.isSpeakingQueue) this._playNextQueue();
  }

  _finishStreamingInput() {
    this.streamCompleted = true;
    // Bug 6 Fix: do not trigger speakOnDone if audio is actively playing or in queue
    const isAudioActive = (this.currentAudio && !this.currentAudio.paused) || (this.synth && this.synth.speaking);
    if (!this.isSpeakingQueue && !isAudioActive && (!this.speakQueue || this.speakQueue.length === 0)) {
      const cb = this.speakOnDone;
      this.speakOnDone = null;
      if (cb) cb();
    }
  }

  _speakViaSynthesis(sentence, onEnd) {
    if (!this.synth) { onEnd(); return; }
    try {
      this.synth.resume();
      const u = new SpeechSynthesisUtterance(sentence);
      const v = this._voiceByName(this.config ? this.config.voiceName : "");
      if (v) u.voice = v;
      if (this.config && this.config.rate) u.rate = Math.max(0.8, Math.min(1.4, this.config.rate));
      if (this.config && this.config.lang) u.lang = this.config.lang;

      let finished = false;
      let timer = null;
      const finish = () => {
        if (finished) return;
        finished = true;
        if (timer) clearTimeout(timer);
        if (window._activeUtterance === u) window._activeUtterance = null;
        onEnd();
      };
      u.onend = finish;
      u.onerror = (e) => { console.warn("SpeechSynthesis error:", e); finish(); };
      window._activeUtterance = u;
      const maxTime = Math.max(3500, sentence.length * 120);
      timer = setTimeout(() => { console.warn("SpeechSynthesis watchdog fired"); finish(); }, maxTime);
      this.synth.speak(u);
      if (this.synth.paused) this.synth.resume();
    } catch (e) {
      console.warn("SpeechSynthesis exception:", e);
      onEnd();
    }
  }

  async _playNextQueue() {
    if (!this.active) return;

    if (!this.speakQueue || this.speakQueue.length === 0) {
      this.isSpeakingQueue = false;
      if (this.streamCompleted) {
        const cb = this.speakOnDone;
        this.speakOnDone = null;
        if (cb) cb();
      }
      return;
    }

    this.isSpeakingQueue = true;
    const gen = this.speakGen;
    const rawSentence = this.speakQueue.shift();
    const sentence = this._cleanSpeech(rawSentence);

    if (!sentence) { this._playNextQueue(); return; }

    if (this.speakQueue.length > 0) this._prefetchAudio(this.speakQueue[0]);

    let handled = false;
    const next = () => {
      if (handled) return;
      handled = true;
      if (this.currentAudio) {
        try { this.currentAudio.pause(); this.currentAudio.src = ""; } catch (e) {}
        this.currentAudio = null;
      }
      if (gen === this.speakGen) this._playNextQueue();
    };

    const voiceName = (this.config && this.config.voiceName) || "en-US-AriaNeural";
    const isNeuralOrNative = voiceName.includes("Neural") || voiceName.includes("david") || voiceName.includes("zira");

    if (!isNeuralOrNative) {
      this._speakViaSynthesis(sentence, next);
      return;
    }

    // Prefetch with 2500ms timeout — falls back to browser synthesis gracefully if backend fails
    try {
      const prefetched = await Promise.race([
        this._prefetchAudio(sentence),
        new Promise((resolve) => setTimeout(() => resolve(null), 2500)),
      ]);

      if (gen !== this.speakGen || !this.active) return;

      if (prefetched && prefetched.url) {
        const { url } = prefetched;
        const player = this.audioPlayer || new Audio();
        this.currentAudio = player;
        this.audioPlayer = player;

        let playerDone = false;
        let playTimer = null;
        const finishAudio = () => {
          if (playerDone) return;
          playerDone = true;
          if (playTimer) clearTimeout(playTimer);
          player.onended = null;
          player.onerror = null;
          URL.revokeObjectURL(url);
          this.audioPreloadCache.delete(sentence);
          next();
        };

        player.onended = finishAudio;
        player.onerror = () => { console.warn("Audio error, falling back to synthesis"); finishAudio(); };
        playTimer = setTimeout(() => { console.warn("Audio timeout, advancing queue"); finishAudio(); }, Math.max(6000, sentence.length * 150));
        player.src = url;
        await player.play();
      } else {
        this._speakViaSynthesis(sentence, next);
      }
    } catch (err) {
      console.warn("Audio play rejected, falling back to synthesis:", err);
      this._speakViaSynthesis(sentence, next);
    }
  }

  _speak(text, onDone) {
    this._startSpeaking(onDone);
    const sentences = this._splitSentences(text);
    sentences.forEach((s) => this._enqueueSentence(s));
    this._finishStreamingInput();
  }

  _onFinal(text) {
    if (!this.active || !text) return;

    // Echo shield: block acoustic reflections of agent's own voice
    if (this._isEchoOfRecentSpeech(text)) {
      console.log("🛡️ [ECHO SHIELD] Suppressed echo:", text);
      this._toListening();
      return;
    }

    const words = text.split(/\s+/).filter(Boolean).length;
    if (words < 1) return;

    // If agent is speaking or thinking, this is a barge-in! Interrupt it.
    if (this.state === "speaking" || this.state === "thinking") {
      console.log("🗣️ [BARGE-IN] Interrupting agent for user speech:", text);
      this._cancelSpeech();
    }

    this._process(text);
  }

  _process(text) {
    if (!this.active) return;
    this._addTurn("user", text);
    this.state = "thinking";
    this.onStatus("Thinking\u2026", "thinking");

    if (this._thinkingTimeout) clearTimeout(this._thinkingTimeout);
    this._thinkingTimeout = setTimeout(() => {
      if (this.state === "thinking" && this.active) {
        console.warn("Thinking watchdog — returning to listening");
        this._toListening();
      }
    }, 12000);

    this._replyStream(text)
      .catch((err) => {
        if (!this.active) return;
        if (err.name !== "AbortError") {
          this._addTurn("agent", "[error] " + err.message);
          this.onStatus("Error \u2014 see transcript", "error");
          this._toListening();
        }
      })
      .finally(() => {
        if (this._thinkingTimeout) { clearTimeout(this._thinkingTimeout); this._thinkingTimeout = null; }
      });
  }

  async _replyStream(userText) {
    this.messages.push({ role: "user", content: userText });

    if (this.currentStreamController) {
      try { this.currentStreamController.abort(); } catch (e) {}
    }
    this.currentStreamController = new AbortController();
    const streamGen = ++this.streamGen;

    let res;
    try {
      res = await fetch("/chat_stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: this.currentStreamController.signal,
        body: JSON.stringify({
          messages: this.messages,
          system: this.config.system,
          agent_id: this.config.agentId || null,
          call_uid: this.config.callUid || null,
        }),
      });
    } catch (err) {
      if (err.name === "AbortError" || streamGen !== this.streamGen) return;
      throw err;
    }

    if (!res.ok) throw new Error("Request failed (HTTP " + res.status + ")");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();

    let fullReply = "";
    let sentenceBuffer = "";
    let hasStartedSpeaking = false;

    while (true) {
      if (streamGen !== this.streamGen) break;
      const { value, done } = await reader.read();
      if (done || streamGen !== this.streamGen) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split("\n");

      for (const line of lines) {
        if (streamGen !== this.streamGen) break;
        if (line.startsWith("data: ")) {
          const dataStr = line.slice(6).trim();
          if (!dataStr) continue;

          let data;
          try { data = JSON.parse(dataStr); } catch (e) { continue; }

          if (data.error) throw new Error(data.error);
          if (data.event) this.onEvent(data.event);

          if (data.text) {
            fullReply += data.text;
            sentenceBuffer += data.text;

            let boundaryMatch;
            while ((boundaryMatch = sentenceBuffer.match(/^([\s\S]*?[.!?\n]+)(?:\s+|$)([\s\S]*)$/))) {
              const completeSentence = this._cleanSpeech(boundaryMatch[1]);
              sentenceBuffer = boundaryMatch[2] || "";
              if (completeSentence) {
                if (!hasStartedSpeaking) {
                  hasStartedSpeaking = true;
                  this._startSpeaking();
                  this.onStatus("Speaking\u2026", "speaking");
                  this._addTurn("agent", "");
                }
                this.lastSpokenText = completeSentence;
                this._enqueueSentence(completeSentence);
              }
            }

            if (hasStartedSpeaking) {
              const cleaned = this._cleanSpeech(fullReply);
              if (cleaned) this._updateLastTurn(cleaned);
            }
          }

          if (data.done) break;
        }
      }
    }

    if (streamGen !== this.streamGen) {
      const partialReply = this._cleanSpeech(fullReply);
      if (partialReply) {
        this.messages.push({ role: "assistant", content: partialReply });
      }
      return;
    }

    const remaining = this._cleanSpeech(sentenceBuffer);
    if (remaining) {
      if (!hasStartedSpeaking) {
        hasStartedSpeaking = true;
        this._startSpeaking();
        this.onStatus("Speaking\u2026", "speaking");
        this._addTurn("agent", "");
      }
      this.lastSpokenText = remaining;
      this._enqueueSentence(remaining);
      sentenceBuffer = "";
    }

    const replyText = this._cleanSpeech(fullReply);
    if (replyText) {
      this.messages.push({ role: "assistant", content: replyText });
      this._updateLastTurn(replyText);
    } else if (!hasStartedSpeaking) {
      const fallback = "I'm listening. How can I help you?";
      this._startSpeaking();
      this.onStatus("Speaking\u2026", "speaking");
      this._addTurn("agent", fallback);
      this.messages.push({ role: "assistant", content: fallback });
      this._enqueueSentence(fallback);
    }

    this._finishStreamingInput();
  }

}

