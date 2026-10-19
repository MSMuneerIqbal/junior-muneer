// Gemini Live calls: the microphone as 16-bit PCM. The AudioContext runs at 16 kHz, so the browser resamples;
// this turns each block into Int16 and sends ~100 ms at a time to the page, which passes it to the backend.
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.chunk = new Int16Array(1600); // 100 ms at 16 kHz
    this.filled = 0;
  }

  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) {
      for (let i = 0; i < channel.length; i++) {
        const s = Math.max(-1, Math.min(1, channel[i]));
        this.chunk[this.filled++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.filled === this.chunk.length) {
          this.port.postMessage(this.chunk.buffer, [this.chunk.buffer]);
          this.chunk = new Int16Array(1600);
          this.filled = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor("pcm-capture", PcmCapture);
