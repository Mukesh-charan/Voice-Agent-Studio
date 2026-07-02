"use strict";

/**
 * CallEngine — one voice conversation loop with optional barge-in.
 *
 *   browser STT -> /chat (LLM + RAG + tools) -> browser TTS -> repeat
 *
 * Modes:
 *   - bargeIn=false: turn-based. Speech captured while the agent is speaking is
 *     ignored, so it never reacts to its own voice.
 *   - bargeIn=true:  the mic stays hot while speaking; if you say 2+ words it
 *     stops talking and listens (best with headphones).
 *
 * Callbacks: onStatus(text, cls), onTurn(role, text), onEvent(event).
 * After a call, read `engine.transcript` ([{role, text}]) to save history.
 */
class CallEngine {
  constructor({ onStatus, onTurn, onEvent } = {}) {
    this.onStatus = onStatus || (() => {});
    this.onTurn = onTurn || (() => {});
    this.onEvent = onEvent || (() => {});
    this.SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    this.synth = window.speechSynthesis;

    this.active = false;
    this.state = "idle"; // idle | listening | thinking | speaking
    this.messages = [];
    this.transcript = [];
    this.recognition = null;
    this.config = null;
    this.speakGen = 0; // bumped to cancel an in-flight sentence chain
  }

  supported() {
    return !!this.SR;
  }

  start(config) {
    this.config = config;
    this.active = true;
    this.messages = [];
    this.transcript = [];
    this._setupRecognition();
    try { this.recognition.start(); } catch (e) {}

    const greeting = (config.greeting || "").trim();
    if (greeting) {
      this._addTurn("agent", greeting);
      this.messages.push({ role: "assistant", content: greeting });
      this.state = "speaking";
      this.onStatus("Speaking…", "speaking");
      this._speak(greeting, () => this._toListening());
    } else {
      this._toListening();
    }
  }

  hangUp() {
    this.active = false;
    this.state = "idle";
    this._cancelSpeech();
    try { this.recognition && this.recognition.stop(); } catch (e) {}
    this.onStatus("Call ended", "");
  }

  // ---------- internals ----------
  _addTurn(role, text) {
    this.transcript.push({ role, text });
    this.onTurn(role, text);
  }

  _toListening() {
    if (!this.active) return;
    this.state = "listening";
    this.onStatus("Listening…", "listening");
  }

  _voiceByName(name) {
    const vs = this.synth.getVoices();
    return vs.find((v) => v.name === name) ||
           vs.find((v) => v.lang && v.lang.startsWith("en")) || null;
  }

  _splitSentences(text) {
    const parts = (text || "").match(/[^.!?]+[.!?]*\s*/g);
    return parts ? parts.map((s) => s.trim()).filter(Boolean) : [text];
  }

  _cancelSpeech() {
    this.speakGen++;
    try { this.synth.cancel(); } catch (e) {}
  }

  // Speak text sentence by sentence so playback starts immediately and can be
  // cut cleanly. onDone fires only if not superseded/cancelled.
  _speak(text, onDone) {
    const gen = ++this.speakGen;
    const queue = this._splitSentences(text);
    const v = this._voiceByName(this.config.voiceName);
    const rate = this.config.rate || 1.0;
    const next = () => {
      if (gen !== this.speakGen || !this.active) return;
      if (!queue.length) { onDone && onDone(); return; }
      const u = new SpeechSynthesisUtterance(queue.shift());
      if (v) u.voice = v;
      u.rate = rate;
      u.onend = () => { if (gen === this.speakGen) next(); };
      u.onerror = () => { if (gen === this.speakGen) next(); };
      this.synth.speak(u);
    };
    try { this.synth.cancel(); } catch (e) {}
    next();
  }

  _onFinal(text) {
    if (!this.active || !text) return;
    const words = text.split(/\s+/).filter(Boolean).length;

    if (this.state === "listening") {
      this._process(text);
    } else if (this.state === "speaking" && this.config.bargeIn && words >= 2) {
      // user talked over the agent — interrupt
      this._cancelSpeech();
      this._process(text);
    }
    // else: thinking, or short echo while speaking → ignore
  }

  _process(text) {
    if (!this.active) return;
    this._addTurn("user", text);
    this.state = "thinking";
    this.onStatus("Thinking…", "thinking");
    this._reply(text)
      .then(({ reply, events }) => {
        if (!this.active) return;
        (events || []).forEach((e) => this.onEvent(e));
        this._addTurn("agent", reply);
        this.state = "speaking";
        this.onStatus("Speaking…", "speaking");
        this._speak(reply, () => this._toListening());
      })
      .catch((err) => {
        if (!this.active) return;
        this._addTurn("agent", "[error] " + err.message);
        this.onStatus("Error — see transcript", "error");
        this._toListening();
      });
  }

  async _reply(userText) {
    this.messages.push({ role: "user", content: userText });
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: this.messages,
        system: this.config.system,
        agent_id: this.config.agentId || null,
        call_uid: this.config.callUid || null,
      }),
    });
    if (!res.ok) {
      let detail = "request failed";
      try { detail = (await res.json()).error || detail; } catch (e) {}
      throw new Error(detail);
    }
    const data = await res.json();
    const reply = (data.reply || "").trim();
    this.messages.push({ role: "assistant", content: reply });
    return { reply, events: data.events || [] };
  }

  _setupRecognition() {
    const rec = new this.SR();
    rec.lang = this.config.lang || "en-US";
    rec.continuous = true;       // stays on through the whole call
    rec.interimResults = true;

    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) this._onFinal(r[0].transcript.trim());
        else interim += r[0].transcript;
      }
      if (interim && this.state === "listening") {
        this.onStatus("Listening… “" + interim.trim() + "”", "listening");
      }
    };

    rec.onend = () => {
      // continuous recognition can still stop (silence/timeout) — restart it
      if (this.active) {
        try { rec.start(); } catch (e) {}
      }
    };

    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      this.onStatus("Mic error: " + e.error, "error");
    };

    this.recognition = rec;
  }
}
