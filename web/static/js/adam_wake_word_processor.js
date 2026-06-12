class AdamAudioProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super(options);
        this.recognizerId = null;
        this.recognizerPort = null;
        this.recognizerSampleRate = 16000;
        this.detectorResampleOffset = 0;
        this.recognizerResampleOffset = 0;
        this.detectorBuffer = new Float32Array(2048);
        this.detectorOffset = 0;
        this.port.onmessage = (event) => {
            if (event.data.action === "startRecognizer") {
                this.recognizerId = event.data.recognizerId;
                this.recognizerPort = event.ports[0];
                this.recognizerSampleRate = event.data.sampleRate || 16000;
                this.recognizerResampleOffset = 0;
            } else if (event.data.action === "stopRecognizer") {
                if (this.recognizerPort) {
                    this.recognizerPort.close();
                }
                this.recognizerId = null;
                this.recognizerPort = null;
            } else if (event.data.action === "preRoll" && this.recognizerPort) {
                const audio = event.data.data.map((sample) => sample * 0x8000);
                this.recognizerPort.postMessage({
                    action: "audioChunk",
                    data: audio,
                    recognizerId: this.recognizerId,
                    sampleRate: event.data.sampleRate,
                }, [audio.buffer]);
            }
        };
    }

    resampleToTarget(samples, offsetName) {
        const inputSampleRate = globalThis.sampleRate || 48000;
        if (inputSampleRate === 16000) {
            return samples;
        }
        const ratio = inputSampleRate / 16000;
        const output = new Float32Array(Math.ceil(samples.length / ratio) + 1);
        let sourcePosition = this[offsetName];
        let outputOffset = 0;
        while (sourcePosition < samples.length) {
            output[outputOffset] = samples[Math.floor(sourcePosition)];
            outputOffset += 1;
            sourcePosition += ratio;
        }
        this[offsetName] = sourcePosition - samples.length;
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
        if (!samples) {
            return true;
        }
        this.sendToDetector(this.resampleToTarget(samples, "detectorResampleOffset"));
        if (this.recognizerPort) {
            const resampled = this.resampleToTarget(samples, "recognizerResampleOffset");
            const audio = resampled.map((sample) => sample * 0x8000);
            this.recognizerPort.postMessage({
                action: "audioChunk",
                data: audio,
                recognizerId: this.recognizerId,
                sampleRate: 16000,
            }, [audio.buffer]);
        }
        return true;
    }
}

registerProcessor("adam-audio-processor", AdamAudioProcessor);
