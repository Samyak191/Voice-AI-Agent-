export class AudioPlayer {
  constructor() {
    this.context = new AudioContext({ sampleRate: 24000 });
    this.nextSeq = 1;
    this.pending = new Map();
    this.playTime = 0;
    this.generation = 0;
    this.activeSources = [];

    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.connect(this.context.destination);
    this._levelBuffer = new Uint8Array(this.analyser.frequencyBinCount);
  }

  async ensureRunning() {
    if (this.context.state === "suspended") {
      await this.context.resume();
    }
  }

  getLevel() {
    this.analyser.getByteTimeDomainData(this._levelBuffer);
    let sum = 0;
    for (let i = 0; i < this._levelBuffer.length; i++) {
      const v = (this._levelBuffer[i] - 128) / 128;
      sum += v * v;
    }
    return Math.sqrt(sum / this._levelBuffer.length);
  }

  _stopActiveSources() {
    for (const source of this.activeSources) {
      try {
        source.stop();
      } catch (e) {
        // already stopped
      }
    }
    this.activeSources = [];
  }

  setGeneration(gen) {
    this._stopActiveSources();
    this.generation = gen;
    this.pending.clear();
    this.nextSeq = 1;
    this.playTime = this.context.currentTime;
  }

  push(arrayBuffer, seq, gen) {
    if (gen !== this.generation) return;
    if (seq < this.nextSeq) return;
    if (this.pending.has(seq)) return;

    this.pending.set(seq, arrayBuffer);

    while (this.pending.has(this.nextSeq)) {
      const buf = this.pending.get(this.nextSeq);
      this.pending.delete(this.nextSeq);
      this._schedule(buf);
      this.nextSeq += 1;
    }
  }

  _schedule(arrayBuffer) {
    const pcm16 = new Int16Array(arrayBuffer);
    const float32 = new Float32Array(pcm16.length);
    for (let i = 0; i < pcm16.length; i++) {
      float32[i] = pcm16[i] / 32768;
    }

    const audioBuffer = this.context.createBuffer(1, float32.length, 24000);
    audioBuffer.copyToChannel(float32, 0);

    const source = this.context.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.analyser);

    const startAt = Math.max(this.playTime, this.context.currentTime);
    source.start(startAt);
    this.playTime = startAt + audioBuffer.duration;

    this.activeSources.push(source);
    source.onended = () => {
      this.activeSources = this.activeSources.filter((s) => s !== source);
    };
  }

  stopAll() {
    this.generation = -1;
    this.pending.clear();
    this.playTime = this.context.currentTime;
    this._stopActiveSources();
  }
}