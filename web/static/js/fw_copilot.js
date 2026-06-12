(function () {
    const copilot = document.querySelector("[data-fw-copilot]");
    if (!copilot) {
        return;
    }

    const status = copilot.querySelector(".fw-copilot-status");
    const logoutLink = document.querySelector("[data-armfirewall-logout]");
    const listeningStorageKey = copilot.dataset.listeningStorageKey;
    const wakeWord = copilot.dataset.wakeWord || "Adam";
    const modelUrl = copilot.dataset.modelUrl;
    const workletUrl = copilot.dataset.workletUrl;
    const configuredConfidence = Number.parseFloat(copilot.dataset.minConfidence);
    const minimumConfidence = Number.isFinite(configuredConfidence)
        ? configuredConfidence
        : 0.70;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    let trackingTimer = null;
    let modelPromise = null;
    let mediaStream = null;
    let audioContext = null;
    let audioSource = null;
    let audioProcessor = null;
    let recognizer = null;
    let recognizerChannel = null;
    let listeningEnabled = false;
    let waitingForCommand = false;
    let wakeWordDetected = false;
    let acceptedWakeConfidence = 0;
    let lastPartialTranscript = "";
    let sessionId = 0;

    function listeningPreference() {
        try {
            return window.localStorage.getItem(listeningStorageKey);
        } catch (error) {
            return null;
        }
    }

    function saveListeningPreference(enabled) {
        try {
            window.localStorage.setItem(listeningStorageKey, String(enabled));
        } catch (error) {
            // Listening still works on the current page when storage is unavailable.
        }
    }

    function clearListeningPreference() {
        try {
            window.localStorage.removeItem(listeningStorageKey);
        } catch (error) {
            // The next login can still request access when storage is unavailable.
        }
    }

    function offlineRecognitionSupportError() {
        if (!window.isSecureContext) {
            return "Microphone is not supported.";
        }
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            return "Microphone is not supported.";
        }
        if (!AudioContextClass || !window.AudioWorkletNode) {
            return "Microphone is not supported.";
        }
        if (!window.WebAssembly || !window.Worker || !window.MessageChannel || !window.indexedDB) {
            return "Microphone is not supported.";
        }
        return null;
    }

    function setState(state, message) {
        copilot.dataset.state = state;
        copilot.setAttribute("aria-label", `Adam: ${message}`);
        if (status) {
            status.textContent = message;
        }
    }

    function setListeningState() {
        copilot.dataset.state = "listening";
        copilot.setAttribute("aria-label", `Adam: Listening for ${wakeWord}`);
        copilot.setAttribute("aria-disabled", "true");
        if (status) {
            status.textContent = "";
        }
    }

    function setSilentState(state, ariaMessage) {
        copilot.dataset.state = state;
        copilot.setAttribute("aria-label", `Adam: ${ariaMessage}`);
        if (status) {
            status.textContent = "";
        }
    }

    function setRequestingMicrophoneState() {
        copilot.dataset.state = "starting";
        copilot.setAttribute("aria-label", "Adam: requesting microphone access");
    }

    function normalizeText(text) {
        return text
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function containsWakeWord(text) {
        const words = normalizeText(text).split(/[^a-z0-9]+/);
        return words.includes(normalizeText(wakeWord));
    }

    function commandAfterWakeWord(text) {
        const expression = new RegExp(`\\b${wakeWord}\\b[\\s,:;.!?-]*`, "i");
        return text.replace(expression, "").trim();
    }

    function wakeWordConfidence(result) {
        const words = Array.isArray(result.result) ? result.result : [];
        const match = words.find((word) => (
            normalizeText(word.word) === normalizeText(wakeWord)
        ));
        return match && Number.isFinite(match.conf) ? match.conf : 0;
    }

    function returnToListening(delay = 1800) {
        window.setTimeout(() => {
            if (listeningEnabled) {
                setListeningState();
            }
        }, delay);
    }

    function rejectSpeech() {
        waitingForCommand = false;
        wakeWordDetected = false;
        acceptedWakeConfidence = 0;
        console.warn("[Adam] Wake word confidence is below the configured minimum.");
        setSilentState("retry", "speech not understood");
        returnToListening(2600);
    }

    function acceptCommand(transcript, command, confidence) {
        waitingForCommand = false;
        wakeWordDetected = false;
        acceptedWakeConfidence = 0;
        console.log("[Adam] Command captured:", { transcript, command, confidence });
        setSilentState("command", "command captured");
        copilot.classList.add("is-pulsing");
        window.setTimeout(() => copilot.classList.remove("is-pulsing"), 700);

        // A future inference layer can listen for this event.
        document.dispatchEvent(new CustomEvent("adam:wake-word", {
            detail: { transcript, command, confidence },
        }));

        returnToListening();
    }

    function processPartialResult(message) {
        const partial = message.result.partial || "";
        if (partial && partial !== lastPartialTranscript) {
            lastPartialTranscript = partial;
            console.log("[Adam] Partial transcript:", partial);
        }
        if (!waitingForCommand && containsWakeWord(partial)) {
            wakeWordDetected = true;
            console.log("[Adam] Wake word detected in partial transcript.");
            setSilentState("awake", "wake word detected");
        }
    }

    function processFinalResult(message) {
        const result = message.result;
        const transcript = (result.text || "").trim();
        lastPartialTranscript = "";
        if (!transcript) {
            return;
        }
        console.log("[Adam] Final transcript:", transcript, result);

        if (waitingForCommand) {
            acceptCommand(transcript, transcript, acceptedWakeConfidence);
            return;
        }

        if (!containsWakeWord(transcript)) {
            if (wakeWordDetected) {
                wakeWordDetected = false;
                setListeningState();
            }
            return;
        }

        const confidence = wakeWordConfidence(result);
        console.log("[Adam] Wake word confidence:", confidence);
        if (confidence < minimumConfidence) {
            rejectSpeech();
            return;
        }

        acceptedWakeConfidence = confidence;
        const command = commandAfterWakeWord(transcript);
        if (command) {
            acceptCommand(transcript, command, confidence);
            return;
        }

        waitingForCommand = true;
        wakeWordDetected = true;
        setSilentState("awake", "wake word detected; listening for command");
    }

    function loadOfflineModel() {
        if (!modelPromise) {
            modelPromise = window.Vosk.createModel(modelUrl).catch((error) => {
                modelPromise = null;
                throw error;
            });
        }
        return modelPromise;
    }

    async function stopAudio() {
        if (recognizer) {
            recognizer.remove();
            recognizer = null;
        }
        if (audioSource) {
            audioSource.disconnect();
            audioSource = null;
        }
        if (audioProcessor) {
            audioProcessor.disconnect();
            audioProcessor = null;
        }
        if (recognizerChannel) {
            recognizerChannel.port1.close();
            recognizerChannel.port2.close();
            recognizerChannel = null;
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        }
        if (audioContext) {
            await audioContext.close();
            audioContext = null;
        }
        console.log("[Adam] Microphone and offline recognizer stopped.");
    }

    async function enableListening() {
        if (!window.Vosk) {
            setState("error", "Microphone is not supported.");
            return;
        }
        const supportError = offlineRecognitionSupportError();
        if (supportError) {
            setState("error", supportError);
            return;
        }

        const currentSession = ++sessionId;
        listeningEnabled = true;
        copilot.setAttribute("aria-pressed", "true");
        copilot.setAttribute("aria-disabled", "false");

        try {
            console.log("[Adam] Requesting microphone access.");
            setRequestingMicrophoneState();
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: false,
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    channelCount: 1,
                },
            });
            console.log("[Adam] Microphone stream is active.");
            audioContext = new AudioContextClass();
            await audioContext.resume();
            if (audioContext.state !== "running") {
                const error = new Error("AudioContext could not be resumed.");
                error.name = "NotAllowedError";
                throw error;
            }
            console.log("[Adam] Audio context is running at", audioContext.sampleRate, "Hz.");

            if (!listeningEnabled || currentSession !== sessionId) {
                await stopAudio();
                return;
            }

            setSilentState("starting", "loading offline voice model");
            console.log("[Adam] Loading the offline Portuguese voice model.");
            const model = await loadOfflineModel();
            console.log("[Adam] Offline Portuguese voice model loaded.");
            if (!listeningEnabled || currentSession !== sessionId) {
                await stopAudio();
                return;
            }

            await audioContext.audioWorklet.addModule(workletUrl);
            console.log("[Adam] Audio worklet loaded.");
            recognizerChannel = new MessageChannel();
            model.registerPort(recognizerChannel.port1);

            recognizer = new model.KaldiRecognizer(audioContext.sampleRate);
            recognizer.on("partialresult", processPartialResult);
            recognizer.on("result", processFinalResult);

            audioProcessor = new AudioWorkletNode(
                audioContext,
                "adam-vosk-processor",
                { channelCount: 1, numberOfInputs: 1, numberOfOutputs: 1 },
            );
            audioProcessor.port.postMessage(
                { action: "init", recognizerId: recognizer.id },
                [recognizerChannel.port2],
            );

            audioSource = audioContext.createMediaStreamSource(mediaStream);
            audioSource.connect(audioProcessor);
            audioProcessor.connect(audioContext.destination);
            saveListeningPreference(true);
            setListeningState();
            console.log(`[Adam] Listening for the wake word "${wakeWord}".`);
        } catch (error) {
            console.error("[Adam] Offline voice recognition failed:", error);
            listeningEnabled = false;
            copilot.setAttribute("aria-pressed", "false");
            copilot.setAttribute("aria-disabled", "false");
            await stopAudio();
            if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
                saveListeningPreference(false);
                setState("muted", "Microphone is not active. Click to enable listening.");
            } else if (error && error.name === "NotFoundError") {
                saveListeningPreference(false);
                setState("error", "Microphone is not supported.");
            } else if (error && error.name === "NotReadableError") {
                setState("error", "Microphone is not supported.");
            } else {
                setState("error", "Microphone is not supported.");
            }
        }
    }

    function setTracking(active) {
        copilot.dataset.tracking = active ? "true" : "false";
    }

    function trackPointer(event) {
        const rect = copilot.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dx = clamp((event.clientX - centerX) / window.innerWidth, -0.5, 0.5);
        const dy = clamp((event.clientY - centerY) / window.innerHeight, -0.5, 0.5);

        copilot.style.setProperty("--copilot-eye-x", `${dx * 4}px`);
        copilot.style.setProperty("--copilot-eye-y", `${dy * 3}px`);
        copilot.style.setProperty("--copilot-glow", String(0.45 + Math.abs(dx) * 0.45));

        setTracking(true);
        window.clearTimeout(trackingTimer);
        trackingTimer = window.setTimeout(() => setTracking(false), 900);
    }

    window.addEventListener("pointermove", trackPointer, { passive: true });
    copilot.addEventListener("click", () => {
        if (!listeningEnabled) {
            enableListening();
        }
    });

    if (logoutLink) {
        logoutLink.addEventListener("click", (event) => {
            event.preventDefault();
            listeningEnabled = false;
            sessionId += 1;
            stopAudio().finally(() => {
                clearListeningPreference();
                window.location.assign(logoutLink.href);
            });
        }, { once: true });
    }

    const savedListeningPreference = listeningPreference();
    if (savedListeningPreference === "true") {
        enableListening();
    } else if (savedListeningPreference === null) {
        setState("muted", "Click to enable listening");
        enableListening();
    } else {
        setState("muted", "Microphone is not active. Click to enable listening.");
    }

    window.addEventListener("pagehide", () => {
        listeningEnabled = false;
        sessionId += 1;
        stopAudio();
        if (modelPromise) {
            modelPromise.then((model) => model.terminate()).catch(() => {});
        }
    });
})();
