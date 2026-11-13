/**
 * vad-processor.js — AudioWorklet processor for low-overhead VAD audio capture.
 * Runs in the isolated audio rendering thread.
 *
 * Bottleneck optimization:
 * Rather than posting every 128 frames (375 postMessages/sec), this accumulates
 * audio samples into 2048-sample blocks (~42.6ms at 48kHz / ~46.4ms at 44.1kHz)
 * before transferring via structured clone. This reduces inter-thread message-passing
 * overhead by >94% and eliminates main thread event loop bottlenecks.
 */
class VadProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 2048;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || !input[0] || input[0].length === 0) return true;

    const channelData = input[0];
    const len = channelData.length;

    for (let i = 0; i < len; i++) {
      this.buffer[this.bufferIndex++] = channelData[i];
      if (this.bufferIndex >= this.bufferSize) {
        const chunk = this.buffer.slice();
        this.port.postMessage({ type: "audio", chunk }, [chunk.buffer]);
        this.bufferIndex = 0;
      }
    }
    return true; // Keep processor alive
  }
}

registerProcessor("vad-processor", VadProcessor);
