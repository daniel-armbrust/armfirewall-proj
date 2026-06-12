class AdamVoskProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super(options);
        this.recognizerId = null;
        this.recognizerPort = null;
        this.port.onmessage = (event) => {
            if (event.data.action === "init") {
                this.recognizerId = event.data.recognizerId;
                this.recognizerPort = event.ports[0];
            }
        };
    }

    process(inputs) {
        const samples = inputs[0][0];
        if (!samples || !this.recognizerPort) {
            return true;
        }

        const audio = samples.map((sample) => sample * 0x8000);
        this.recognizerPort.postMessage(
            {
                action: "audioChunk",
                data: audio,
                recognizerId: this.recognizerId,
                sampleRate,
            },
            [audio.buffer],
        );
        return true;
    }
}

registerProcessor("adam-vosk-processor", AdamVoskProcessor);
