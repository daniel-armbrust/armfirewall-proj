class AdamAudioProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.detectorResampleOffset = 0;
        this.detectorBuffer = new Float32Array(2048);
        this.detectorOffset = 0;
    }

    resampleToTarget(samples) {
        const inputSampleRate = globalThis.sampleRate || 48000;
        if (inputSampleRate === 16000) {
            return samples;
        }
        const ratio = inputSampleRate / 16000;
        const output = new Float32Array(Math.ceil(samples.length / ratio) + 1);
        let sourcePosition = this.detectorResampleOffset;
        let outputOffset = 0;
        while (sourcePosition < samples.length) {
            output[outputOffset] = samples[Math.floor(sourcePosition)];
            outputOffset += 1;
            sourcePosition += ratio;
        }
        this.detectorResampleOffset = sourcePosition - samples.length;
        return output.subarray(0, outputOffset);
    }

    sendToDetector(samples) {
        let sourceOffset = 0;
        while (sourceOffset < samples.length) {
            const available = this.detectorBuffer.length - this.detectorOffset;
            const length = Math.min(available, samples.length - sourceOffset);
            this.detectorBuffer.set(samples.subarray(sourceOffset, sourceOffset + length), this.detectorOffset);
            this.detectorOffset += length;
            sourceOffset += length;
            if (this.detectorOffset === this.detectorBuffer.length) {
                const chunk = this.detectorBuffer;
                this.port.postMessage({ action: "audio", data: chunk, sampleRate: 16000 }, [chunk.buffer]);
                this.detectorBuffer = new Float32Array(2048);
                this.detectorOffset = 0;
            }
        }
    }

    process(inputs) {
        const samples = inputs[0][0];
        if (samples) {
            this.sendToDetector(this.resampleToTarget(samples));
        }
        return true;
    }
}

registerProcessor("adam-audio-processor", AdamAudioProcessor);
