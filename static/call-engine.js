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

  setDeaf(durationMs = 0) {
    if (this._deafTimer) clearTimeout(this._deafTimer);
    this.isDeaf = true;
    this.isRecording = false;
    this.audioBuffer = [];
    this.silenceSamples = 0;
    if (durationMs > 0) {
      this._deafTimer = setTimeout(() => {
        this.isDeaf = false;
        this._deafTimer = null;
      }, durationMs);
    }
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
      const silenceSampleLimit = Math.floor(sampleRate * 0.85); // 850ms natural conversational pause
      const minUtteranceSamples = Math.floor(sampleRate * 0.30); // 300ms minimum speech
      const maxUtteranceSamples = Math.floor(sampleRate * 20.0); // 20s maximum utterance

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
          // Clear pre-roll continuously during speaking so speaker voice never leaks into user buffer
          this.preRollRing = [];

          // Track speaker acoustic bleed volume
          this.speakerBleedRms = (this.speakerBleedRms || 0.016) * 0.90 + rms * 0.10;

          // Grace period: First 600ms after speech begins, reject barge-in to avoid tripping on initial speaker transient
          const timeSinceSpeak = Date.now() - (this.turnSpeakStartedAt || this.speakStartedAt || 0);
          if (timeSinceSpeak < 600) {
            this._bargeInHits = 0;
            return;
          }

          this.speakerBleedRms = Math.max(0.012, (this.speakerBleedRms || 0.015) * 0.95 + rms * 0.05);
          // Human barge-in must be significantly louder than speaker bleed (2.2x dynamic multiplier)
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

        // If AGENT IS THINKING: Allow user speech to interrupt thinking state
        if (state === "thinking") {
          const thinkingThreshold = Math.max(0.024, this.noiseFloor * 1.6);
          if (rms > thinkingThreshold) {
            this._bargeInHits = (this._bargeInHits || 0) + 1;
            if (this._bargeInHits >= 3) {
              console.log(`🗣️ [BARGE-IN] Interrupted thinking state with user voice (RMS ${rms.toFixed(4)})`);
              this._bargeInHits = 0;
              if (this.onBargeIn) {
                this.onBargeIn(inputData);
              }
            }
          } else {
            this._bargeInHits = Math.max(0, (this._bargeInHits || 0) - 1);
          }
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
        this.speakerBleedRms = 0.012;

        // 2. If AGENT IS THINKING OR LISTENING:
        if (this.isTranscribing) return;

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
      formData.append("prompt", "Conversational English voice call: appointments, phone numbers, digits 0-9, mobile numbers, bookings, schedule, names, dates.");

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
    this.callStartTime = Date.now();
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
      this.isGreeting = true;
      this._registerSpokenText(greeting);
      this._addTurn("agent", greeting);
      this.messages.push({ role: "assistant", content: greeting });
      this.state = "speaking";
      this.lastSpokenText = greeting;
      this.lastSpokenAt = Date.now();
      this.onStatus("Speaking\u2026", "speaking");
      this._speak(greeting, () => {
        this.isGreeting = false;
        this._toListening();
      });
    } else {
      this.isGreeting = false;
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
    if (this.isGreeting) return; // Never barge-in during initial greeting
    if (Date.now() - (this.callStartTime || 0) < 600) return; // Settle for AEC
    if (this.config && (this.config.bargeIn === 0 || this.config.bargeIn === false)) return;

    console.log("⚡ [BARGE-IN] Interrupted agent speech by user voice!");
    this.speechEndedAt = Date.now();
    this._cancelSpeech();
    this.state = "listening";
    this.onStatus("Listening\u2026", "listening");

    if (this.localSTT) {
      this.localSTT.isRecording = false;
      this.localSTT.audioBuffer = [];
      this.localSTT.preRollRing = [];
      this.localSTT.silenceSamples = 0;
      this.localSTT.setDeaf(200); // Mute 200ms to discard physical speaker cut-off click
      this.localSTT._bargeInHits = 0;
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
      this.localSTT.setDeaf(450); // Mute mic for 450ms while physical speaker decay finishes
      this.localSTT.isRecording = false;
      this.localSTT.audioBuffer = [];
      this.localSTT.preRollRing = [];
      this.localSTT.silenceSamples = 0;
      if (this._cooldownTimer) { clearTimeout(this._cooldownTimer); this._cooldownTimer = null; }
    }
  }

  _registerSpokenText(text) {
    if (!text) return;
    const clean = text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
    if (!clean) return;
    this.lastSpokenText = clean;
    this.lastSpokenAt = Date.now();
    if (!this.recentSpokenPhrases) this.recentSpokenPhrases = [];
    this.recentSpokenPhrases.push({ text: clean, at: Date.now() });
    if (this.recentSpokenPhrases.length > 10) this.recentSpokenPhrases.shift();
  }

  _isEchoOfRecentSpeech(text) {
    if (!text) return false;
    const cleanText = text.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
    if (!cleanText) return false;

    // Check against all bot phrases spoken in last 5.0 seconds
    const now = Date.now();
    const recent = (this.recentSpokenPhrases || []).filter((p) => now - p.at < 5000);
    if (!recent.length && this.lastSpokenText && now - (this.lastSpokenAt || 0) < 5000) {
      recent.push({ text: this.lastSpokenText, at: this.lastSpokenAt });
    }

    if (!recent.length) return false;

    const userWords = cleanText.split(/\s+/).filter(Boolean);

    for (const phraseObj of recent) {
      const phrase = phraseObj.text;
      // Exact match or substring match (e.g. "thanks for" within "hi thanks for calling...")
      if (cleanText === phrase || (phrase.includes(cleanText) && cleanText.length >= 6) || (cleanText.includes(phrase) && phrase.length >= 6)) {
        console.log(`🛡️ [ECHO SHIELD] Suppressed speaker echo: "${cleanText}" matches "${phrase}"`);
        return true;
      }

      // Overlap test on phrases >= 2 words
      if (userWords.length >= 2) {
        const pWords = new Set(phrase.split(/\s+/));
        let matchCount = 0;
        for (const w of userWords) {
          if (pWords.has(w)) matchCount++;
        }
        if (matchCount / userWords.length >= 0.50) {
          console.log(`🛡️ [ECHO SHIELD] Suppressed speaker echo (${matchCount}/${userWords.length} words): "${cleanText}"`);
          return true;
        }
      }
    }

    return false;
  }

  _voiceByName(name) {
    if (!this.synth) return null;
    const vs = this.synth.getVoices() || [];
    if (!vs.length) return null;

    const isMale = name && /david|male|guy|george/i.test(name);
    const n = (name || "").toLowerCase();

    // 1. Exact match
    let match = vs.find((v) => v.name === name || v.voiceURI === name);
    if (match) return match;

    // 2. Named matches
    if (n.includes("zira")) match = vs.find((v) => v.name.toLowerCase().includes("zira"));
    else if (n.includes("david")) match = vs.find((v) => v.name.toLowerCase().includes("david"));
    else if (n.includes("aria") || n.includes("natural")) match = vs.find((v) => v.name.toLowerCase().includes("aria") || v.name.toLowerCase().includes("natural"));
    else if (n.includes("jenny")) match = vs.find((v) => v.name.toLowerCase().includes("jenny"));
    if (match) return match;

    // 3. Name contains query
    if (n) {
      match = vs.find((v) => v.name.toLowerCase().includes(n));
      if (match) return match;
    }

    // 4. Gender-consistent match with language preference (protect against defaulting female -> David)
    const lang = (this.config && this.config.lang) ? this.config.lang.toLowerCase().slice(0, 2) : "en";
    const langVoices = vs.filter((v) => v.lang && v.lang.toLowerCase().startsWith(lang));
    const pool = langVoices.length > 0 ? langVoices : vs;

    if (!isMale) {
      const femaleInPool = pool.find((v) => /zira|aria|jenny|female|samantha|victoria|susan|hazel|heera/i.test(v.name));
      if (femaleInPool) return femaleInPool;
      const anyFemale = vs.find((v) => /zira|aria|jenny|female|samantha|victoria|susan|hazel|heera/i.test(v.name));
      if (anyFemale) return anyFemale;
    } else {
      const maleInPool = pool.find((v) => /david|male|guy|george|mark|ravi/i.test(v.name));
      if (maleInPool) return maleInPool;
    }

    return pool[0] || vs[0];
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
    if (!s) return [];

    // Protect decimal numbers like 3.14 or 10.50
    s = s.replace(/(\d+)\.(\d+)/g, "$1___DEC___$2");

    // Protect common abbreviations with dot
    const abbrevMap = {};
    let counter = 0;
    const abbrevs = ["a.m.", "p.m.", "dr.", "mr.", "mrs.", "ms.", "rs.", "e.g.", "i.e.", "vs.", "etc.", "approx."];
    for (const ab of abbrevs) {
      const escaped = ab.replace(/\./g, "\\.");
      const regex = new RegExp("\\b" + escaped, "gi");
      s = s.replace(regex, (m) => {
        const token = `___AB${counter++}___`;
        abbrevMap[token] = m;
        return token;
      });
    }

    // Ensure space after punctuation if directly followed by letter
    s = s.replace(/([.!?]+)(?=[A-Za-z])/g, "$1 ");

    // Split on sentence boundaries using lookbehind (keeps all sentences/clauses even if no trailing punctuation)
    let rawParts = s.split(/(?<=[.!?\n]+)\s+/);

    // Clause split: if any part is over 160 characters, split at natural comma or semicolon for low TTS latency
    const clauseParts = [];
    for (const part of rawParts) {
      if (part.length > 160 && /[,;:]\s+/.test(part)) {
        const sub = part.split(/(?<=[,;:])\s+/);
        clauseParts.push(...sub);
      } else {
        clauseParts.push(part);
      }
    }
    rawParts = clauseParts;

    return rawParts.map((part) => {
      let restored = part;
      for (const [token, orig] of Object.entries(abbrevMap)) {
        restored = restored.replace(new RegExp(token, "g"), orig);
      }
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
    this.lastEnqueuedSentence = "";
    this.isGreeting = false;
    this.speechEndedAt = Date.now();

    if (this.currentAudio) {
      try {
        this.currentAudio.onended = null;
        this.currentAudio.onerror = null;
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = "";
      } catch (e) {}
      this.currentAudio = null;
    }
    if (this.audioPlayer) {
      try {
        this.audioPlayer.onended = null;
        this.audioPlayer.onerror = null;
        this.audioPlayer.pause();
        this.audioPlayer.currentTime = 0;
        this.audioPlayer.src = "";
      } catch (e) {}
      this.audioPlayer = null;
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
    this.lastEnqueuedSentence = "";
    if (this.currentAudio) {
      try {
        this.currentAudio.onended = null;
        this.currentAudio.onerror = null;
        this.currentAudio.pause();
        this.currentAudio.currentTime = 0;
        this.currentAudio.src = "";
      } catch (e) {}
      this.currentAudio = null;
    }
    if (this.audioPlayer) {
      try {
        this.audioPlayer.onended = null;
        this.audioPlayer.onerror = null;
        this.audioPlayer.pause();
        this.audioPlayer.currentTime = 0;
        this.audioPlayer.src = "";
      } catch (e) {}
      this.audioPlayer = null;
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
    this.lastEnqueuedSentence = "";
    if (this.localSTT) {
      this.localSTT.turnSpeakStartedAt = Date.now();
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

    // Repetition shield: prevent enqueuing duplicate sentence back-to-back
    if (this.lastEnqueuedSentence && this.lastEnqueuedSentence.toLowerCase() === sentence.toLowerCase()) {
      console.warn("🛡️ [REPETITION SHIELD] Blocked duplicate sentence enqueue:", sentence);
      return;
    }
    if (this.speakQueue && this.speakQueue.length > 0 && this.speakQueue[this.speakQueue.length - 1].toLowerCase() === sentence.toLowerCase()) {
      console.warn("🛡️ [REPETITION SHIELD] Blocked duplicate queue entry:", sentence);
      return;
    }
    this.lastEnqueuedSentence = sentence;

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
      try { this.synth.cancel(); } catch (e) {}
      this.synth.speak(u);
      if (this.synth.paused) this.synth.resume();
    } catch (e) {
      console.warn("SpeechSynthesis exception:", e);
      onEnd();
    }
  }

  async _playNextQueue() {
    if (!this.active) return;
    if (this.isSpeakingQueue) return;

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

    if (!sentence) {
      this.isSpeakingQueue = false;
      this._playNextQueue();
      return;
    }

    // Kick off prefetch of next sentence while this one plays
    if (this.speakQueue.length > 0) this._prefetchAudio(this.speakQueue[0]);

    let handled = false;
    const next = () => {
      if (handled) return;
      handled = true;
      if (this.currentAudio) {
        try {
          this.currentAudio.onloadedmetadata = null;
          this.currentAudio.onended = null;
          this.currentAudio.onerror = null;
          this.currentAudio.pause();
          this.currentAudio.src = "";
        } catch (e) {}
        this.currentAudio = null;
      }
      this.isSpeakingQueue = false;
      if (gen === this.speakGen && this.active) {
        this._playNextQueue();
      }
    };

    const voiceName = (this.config && this.config.voiceName) || "en-US-AriaNeural";
    const isNeural = voiceName.includes("Neural");

    if (!isNeural) {
      if (this.localSTT) {
        this.localSTT.speakStartedAt = Date.now();
        this.localSTT._bargeInHits = 0;
      }
      this._speakViaSynthesis(sentence, next);
      return;
    }

    let prefetched = null;
    try {
      // 10s TTS timeout to allow complex sentences to synthesize cleanly without falling back
      prefetched = await Promise.race([
        this._prefetchAudio(sentence),
        new Promise((resolve) => setTimeout(() => resolve(null), 10000)),
      ]);
    } catch (_) { prefetched = null; }

    if (gen !== this.speakGen || !this.active) {
      this.isSpeakingQueue = false;
      return;
    }

    if (prefetched && prefetched.url) {
      const { url } = prefetched;
      const audio = new Audio();
      this.currentAudio = audio;

      let playerDone = false;
      let fallbackTimerId = null;
      let durationTimerId = null;

      const finishAudio = () => {
        if (playerDone) return;
        playerDone = true;
        // Clear both timers deterministically
        if (fallbackTimerId !== null) { clearTimeout(fallbackTimerId); fallbackTimerId = null; }
        if (durationTimerId !== null) { clearTimeout(durationTimerId); durationTimerId = null; }
        try {
          audio.onloadedmetadata = null;
          audio.onended = null;
          audio.onerror = null;
          audio.pause();
          audio.src = "";
        } catch (e) {}
        URL.revokeObjectURL(url);
        this.audioPreloadCache.delete(sentence);
        next();
      };

      // Duration-based watchdog set once metadata is available
      audio.onloadedmetadata = () => {
        const dur = (audio.duration && isFinite(audio.duration)) ? audio.duration * 1000 : 8000;
        durationTimerId = setTimeout(() => {
          console.warn("[TTS] Duration watchdog reached");
          finishAudio();
        }, dur + 2500);
      };

      // Hard cap fallback — only fires if onloadedmetadata never arrives
      fallbackTimerId = setTimeout(() => {
        console.warn("[TTS] Hard cap watchdog reached");
        finishAudio();
      }, Math.max(12000, sentence.length * 180));

      audio.onended = finishAudio;
      audio.onerror = (e) => {
        console.warn("[TTS] Audio error:", e);
        finishAudio();
      };

      audio.src = url;
      if (this.localSTT) {
        this.localSTT.speakStartedAt = Date.now();
        this.localSTT._bargeInHits = 0;
      }
      try {
        await audio.play();
      } catch (err) {
        if (err.name !== "AbortError") console.warn("[TTS] play() rejected:", err);
        finishAudio();
      }
    } else {
      // TTS unavailable — fall back to browser synthesis for this sentence only
      console.warn("[TTS] Server TTS unavailable, using synthesis fallback for:", sentence);
      if (this.localSTT) {
        this.localSTT.speakStartedAt = Date.now();
        this.localSTT._bargeInHits = 0;
      }
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

    const trimmed = text.trim();
    // Debounce duplicate user transcripts within 2.5s
    if (this.lastFinalText && this.lastFinalText.toLowerCase() === trimmed.toLowerCase() && Date.now() - (this.lastFinalAt || 0) < 2500) {
      console.log("🛡️ [DEBOUNCE] Ignored duplicate transcription:", trimmed);
      return;
    }
    this.lastFinalText = trimmed;
    this.lastFinalAt = Date.now();

    // Echo shield: block acoustic reflections of agent's own voice
    if (this._isEchoOfRecentSpeech(trimmed)) {
      console.log("🛡️ [ECHO SHIELD] Suppressed echo:", trimmed);
      this._toListening();
      return;
    }

    const words = trimmed.split(/\s+/).filter(Boolean).length;
    if (words < 1) return;

    // If agent is speaking or thinking, this is a barge-in! Interrupt it.
    if (this.state === "speaking" || this.state === "thinking") {
      console.log("🗣️ [BARGE-IN] Interrupting agent for user speech:", trimmed);
      this._cancelSpeech();
    }

    this._process(trimmed);
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
              const matchedPart = boundaryMatch[1];
              const rest = boundaryMatch[2] || "";

              // If the matched punctuation is part of an abbreviation (e.g. Dr., Mr., a.m.), wait for the true sentence end
              if (/\b(?:dr|mr|mrs|ms|rs|eg|ie|vs|a\.m|p\.m)\.$/i.test(matchedPart.trim())) {
                const nextMatch = rest.match(/^([\s\S]*?[.!?\n]+)(?:\s+|$)([\s\S]*)$/);
                if (nextMatch) {
                  const combined = this._cleanSpeech(matchedPart + " " + nextMatch[1]);
                  sentenceBuffer = nextMatch[2] || "";
                  if (combined) {
                    if (!hasStartedSpeaking) {
                      hasStartedSpeaking = true;
                      this._startSpeaking();
                      this.onStatus("Speaking\u2026", "speaking");
                      this._addTurn("agent", "");
                    }
                    this.lastSpokenText = combined;
                    this._enqueueSentence(combined);
                  }
                  continue;
                } else {
                  break;
                }
              }

              const completeSentence = this._cleanSpeech(matchedPart);
              sentenceBuffer = rest;
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

