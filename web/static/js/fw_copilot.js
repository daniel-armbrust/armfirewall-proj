(function () {
    const copilot = document.querySelector("[data-fw-copilot]");
    if (!copilot) {
        return;
    }

    const status = copilot.querySelector(".fw-copilot-status");
    const logoutLink = document.querySelector("[data-armfirewall-logout]");
    const listeningStorageKey = copilot.dataset.listeningStorageKey;
    const speechLanguage = copilot.dataset.speechLanguage || "en-US";
    const wakeWord = copilot.dataset.wakeWord || "Adam";
    const wakeWordAliases = (copilot.dataset.wakeWordAliases || "")
        .split(",")
        .map((alias) => alias.trim())
        .filter(Boolean);
    const wakeWords = Array.from(new Set([wakeWord, ...wakeWordAliases]));
    const wakeTranscriptionAliases = (copilot.dataset.wakeTranscriptionAliases || "")
        .split(",")
        .map((alias) => alias.trim())
        .filter(Boolean);
    const spokenWakeWord = wakeWordAliases[0] || wakeWord;
    const wakeProfileKey = copilot.dataset.wakeProfileKey || "default";
    const modelUrl = copilot.dataset.modelUrl;
    const workletUrl = copilot.dataset.workletUrl;
    const detectorWorkerUrl = copilot.dataset.detectorWorkerUrl;
    const minConfidence = Number.parseFloat(copilot.dataset.minConfidence) || 0.70;
    const enrollmentSamples = Number.parseInt(copilot.dataset.enrollmentSamples, 10) || 5;
    const enrollmentDurationMs = Number.parseInt(copilot.dataset.enrollmentDurationMs, 10) || 1200;
    const detectionIntervalMs = Number.parseInt(copilot.dataset.detectionIntervalMs, 10) || 250;
    const requiredDetectionStreak = Number.parseInt(copilot.dataset.detectionStreak, 10) || 3;
    const thresholdMultiplier = Number.parseFloat(copilot.dataset.detectionThresholdMultiplier) || 1.6;
    const preRollMs = Number.parseInt(copilot.dataset.preRollMs, 10) || 1600;
    const commandMinCaptureMs = Number.parseInt(copilot.dataset.commandMinCaptureMs, 10) || 1200;
    const commandSampleRate = Number.parseInt(copilot.dataset.commandSampleRate, 10) || 16000;
    const commandSilenceThreshold = Number.parseFloat(copilot.dataset.commandSilenceThreshold) || 0.012;
    const commandTimeoutMs = Number.parseInt(copilot.dataset.commandTimeoutMs, 10) || 8000;
    const commandTrailingSilenceMs = Number.parseInt(
        copilot.dataset.commandTrailingSilenceMs,
        10,
    ) || 900;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    let trackingTimer = null;
    let wakeAlertTimer = null;
    let modelPromise = null;
    let mediaStream = null;
    let audioContext = null;
    let audioSource = null;
    let audioProcessor = null;
    let detectorWorker = null;
    let detectorReady = false;
    let detectorEnrolled = false;
    let enrollmentInProgress = false;
    let enrollmentCompletedSamples = 0;
    let recognizer = null;
    let recognizerChannel = null;
    let commandTimeout = null;
    let commandSilenceTimer = null;
    let commandStartedAt = 0;
    let commandSpeechDetected = false;
    let commandResultSegments = [];
    let recognizerRemovalRequested = false;
    let commandConfidence = 0;
    let listeningEnabled = false;
    let commandRecognitionActive = false;
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
            // The current page can still listen when storage is unavailable.
        }
    }

    function clearListeningPreference() {
        try {
            window.localStorage.removeItem(listeningStorageKey);
        } catch (error) {
            // The next login can still request access when storage is unavailable.
        }
    }

    function supportError() {
        if (!window.isSecureContext
            || !navigator.mediaDevices
            || !navigator.mediaDevices.getUserMedia
            || !AudioContextClass
            || !window.AudioWorkletNode
            || !window.WebAssembly
            || !window.Worker
            || !window.MessageChannel
            || !window.indexedDB) {
            return "Microphone is not supported.";
        }
        return null;
    }

    function setState(state, message) {
        window.clearTimeout(wakeAlertTimer);
        wakeAlertTimer = null;
        copilot.dataset.state = state;
        copilot.setAttribute("aria-label", `Adam: ${message}`);
        if (status) {
            status.textContent = message;
        }
    }

    function setSilentState(state, ariaMessage) {
        window.clearTimeout(wakeAlertTimer);
        wakeAlertTimer = null;
        copilot.dataset.state = state;
        copilot.setAttribute("aria-label", `Adam: ${ariaMessage}`);
        if (status) {
            status.textContent = "";
        }
    }

    function setListeningState() {
        setSilentState("listening", `listening for ${wakeWord}`);
        copilot.setAttribute("aria-pressed", "true");
        copilot.setAttribute("aria-disabled", "true");
    }

    function setEnrollmentPrompt() {
        setState("muted", "Click to teach Adam the wake word.");
        copilot.setAttribute("aria-disabled", "false");
    }

    function setWakeAlertState() {
        window.clearTimeout(wakeAlertTimer);
        copilot.dataset.state = "wake-alert";
        copilot.setAttribute(
            "aria-label",
            "Adam: wake word detected; listening for command",
        );
        if (status) {
            status.textContent = "!";
        }
        wakeAlertTimer = window.setTimeout(() => {
            wakeAlertTimer = null;
            if (copilot.dataset.state === "wake-alert") {
                setSilentState("command", "listening for command");
            }
        }, 1200);
    }

    function normalizeText(text) {
        return text
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .toLowerCase()
            .trim();
    }

    function escapeRegularExpression(value) {
        return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function commandAfterWakeWord(text) {
        const recognizedWakeWords = Array.from(new Set([
            ...wakeWords,
            ...wakeTranscriptionAliases,
            ...wakeWords.map((word) => normalizeText(word)),
            ...wakeTranscriptionAliases.map((word) => normalizeText(word)),
        ]));
        const alternatives = recognizedWakeWords
            .sort((left, right) => right.length - left.length)
            .map((word) => escapeRegularExpression(word))
            .join("|");
        const expression = new RegExp(`^\\s*(?:${alternatives})\\b[\\s,:;.!?-]*`, "i");
        return text.replace(expression, "").trim();
    }

    function loadOfflineModel() {
        if (!modelPromise) {
            modelPromise = window.Vosk.createModel(modelUrl)
                .catch((error) => {
                    modelPromise = null;
                    throw error;
                });
        }
        return modelPromise;
    }

    function forwardAudioToDetector(event) {
        if (!detectorWorker || event.data.action !== "audio") {
            return;
        }
        const audio = event.data.data;
        observeCommandAudio(audio);
        detectorWorker.postMessage({
            type: "audio",
            data: audio,
            sampleRate: event.data.sampleRate,
        }, [audio.buffer]);
    }

    function audioLevel(audio) {
        if (!audio.length) {
            return 0;
        }
        let energy = 0;
        for (const sample of audio) {
            energy += sample * sample;
        }
        return Math.sqrt(energy / audio.length);
    }

    function observeCommandAudio(audio) {
        if (!commandRecognitionActive
            || recognizerRemovalRequested
            || audioLevel(audio) < commandSilenceThreshold) {
            return;
        }
        commandSpeechDetected = true;
        window.clearTimeout(commandSilenceTimer);
        const elapsed = performance.now() - commandStartedAt;
        const remainingMinimum = Math.max(0, commandMinCaptureMs - elapsed);
        commandSilenceTimer = window.setTimeout(
            finishCommandCapture,
            Math.max(commandTrailingSilenceMs, remainingMinimum),
        );
    }

    function finishCommandCapture() {
        window.clearTimeout(commandSilenceTimer);
        commandSilenceTimer = null;
        if (!commandRecognitionActive || recognizerRemovalRequested) {
            return;
        }
        if (!commandSpeechDetected || !recognizer) {
            stopCommandRecognition();
            return;
        }
        recognizerRemovalRequested = true;
        if (audioProcessor) {
            audioProcessor.port.postMessage({ action: "stopRecognizer" });
        }
        recognizer.remove();
    }

    function scheduleEnrollmentSample(sampleNumber, delay = 700) {
        if (!enrollmentInProgress || !detectorWorker) {
            return;
        }
        setState(
            "awake",
            `Say “${spokenWakeWord}” now (${sampleNumber}/${enrollmentSamples}).`,
        );
        window.setTimeout(() => {
            if (enrollmentInProgress && detectorWorker) {
                detectorWorker.postMessage({ type: "recordEnrollmentSample" });
            }
        }, delay);
    }

    function startEnrollment() {
        if (!detectorReady || detectorEnrolled || enrollmentInProgress || !detectorWorker) {
            return;
        }
        enrollmentInProgress = true;
        enrollmentCompletedSamples = 0;
        copilot.setAttribute("aria-disabled", "true");
        detectorWorker.postMessage({ type: "startEnrollment" });
    }

    async function stopCommandRecognition({ resumeDetector = true } = {}) {
        window.clearTimeout(commandTimeout);
        window.clearTimeout(commandSilenceTimer);
        commandTimeout = null;
        commandSilenceTimer = null;
        commandRecognitionActive = false;
        if (audioProcessor) {
            audioProcessor.port.postMessage({ action: "stopRecognizer" });
        }
        if (recognizer && !recognizerRemovalRequested) {
            recognizer.remove();
        }
        recognizer = null;
        recognizerRemovalRequested = false;
        commandStartedAt = 0;
        commandSpeechDetected = false;
        commandResultSegments = [];
        if (recognizerChannel) {
            recognizerChannel.port1.close();
            recognizerChannel = null;
        }
        if (resumeDetector && detectorWorker) {
            detectorWorker.postMessage({ type: "resumeDetection" });
            setListeningState();
        }
    }

    function acceptCommand(transcript, command) {
        if (!commandRecognitionActive) {
            return;
        }
        commandRecognitionActive = false;
        setSilentState("command", "command captured");
        copilot.classList.add("is-pulsing");
        window.setTimeout(() => copilot.classList.remove("is-pulsing"), 700);
        document.dispatchEvent(new CustomEvent("adam:wake-word", {
            detail: { transcript, command, confidence: commandConfidence },
        }));
        stopCommandRecognition();
    }

    async function sendTranscription(event) {
        const text = (event.detail.command || event.detail.transcript || "").trim();
        if (!text) {
            return;
        }
        try {
            await window.fetch("/api/adam/transcription", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, language: speechLanguage }),
            });
        } catch {
            // Transcription delivery is intentionally silent in this initial version.
        }
    }

    function processCommandResult(message) {
        if (!commandRecognitionActive
            || !recognizer
            || message.recognizerId !== recognizer.id) {
            return;
        }
        const segment = (message.result.text || "").trim();
        if (segment && commandResultSegments.at(-1) !== segment) {
            commandResultSegments.push(segment);
        }
        if (!recognizerRemovalRequested) {
            return;
        }
        const transcript = commandResultSegments.join(" ").trim();
        if (!transcript) {
            stopCommandRecognition();
            return;
        }
        const command = commandAfterWakeWord(transcript);
        if (command) {
            acceptCommand(transcript, command);
        }
    }

    async function startCommandRecognition(message) {
        if (commandRecognitionActive || !audioProcessor || !audioContext) {
            return;
        }
        commandRecognitionActive = true;
        commandConfidence = message.score;
        commandStartedAt = performance.now();
        commandSpeechDetected = false;
        commandResultSegments = [];
        recognizerRemovalRequested = false;
        setWakeAlertState();
        copilot.classList.add("is-pulsing");
        window.setTimeout(() => copilot.classList.remove("is-pulsing"), 700);
        try {
            const model = await loadOfflineModel();
            if (!commandRecognitionActive) {
                return;
            }
            recognizerChannel = new MessageChannel();
            model.registerPort(recognizerChannel.port1);
            recognizer = new model.KaldiRecognizer(commandSampleRate);
            const activeRecognizer = recognizer;
            recognizer.on("result", (result) => {
                if (recognizer === activeRecognizer) {
                    processCommandResult(result);
                }
            });
            audioProcessor.port.postMessage({
                action: "startRecognizer",
                recognizerId: recognizer.id,
                sampleRate: commandSampleRate,
            }, [recognizerChannel.port2]);
            const preRoll = message.preRoll;
            audioProcessor.port.postMessage({
                action: "preRoll",
                data: preRoll,
                sampleRate: 16000,
            }, [preRoll.buffer]);
            commandTimeout = window.setTimeout(() => {
                finishCommandCapture();
            }, commandTimeoutMs);
        } catch {
            stopCommandRecognition();
        }
    }

    function handleDetectorMessage(event) {
        const message = event.data;
        if (message.type === "ready") {
            detectorReady = true;
            detectorEnrolled = message.enrolled;
            if (detectorEnrolled) {
                setListeningState();
            } else {
                setEnrollmentPrompt();
            }
        } else if (message.type === "enrollmentReady") {
            scheduleEnrollmentSample(1);
        } else if (message.type === "enrollmentSampleComplete") {
            enrollmentCompletedSamples = message.count;
            if (message.count < enrollmentSamples) {
                scheduleEnrollmentSample(message.count + 1, 900);
            }
        } else if (message.type === "enrollmentTooQuiet") {
            setState("retry", `I couldn't hear you. Say “${spokenWakeWord}” again.`);
            const nextSample = Math.min(enrollmentSamples, enrollmentCompletedSamples + 1);
            scheduleEnrollmentSample(nextSample, 1200);
        } else if (message.type === "enrollmentComplete") {
            enrollmentInProgress = false;
            detectorEnrolled = true;
            setListeningState();
        } else if (message.type === "wakeWord") {
            if (message.score >= minConfidence) {
                startCommandRecognition(message);
            } else if (detectorWorker) {
                detectorWorker.postMessage({ type: "resumeDetection" });
                setListeningState();
            }
        }
    }

    function initializeDetector() {
        detectorWorker = new Worker(detectorWorkerUrl);
        detectorWorker.onmessage = handleDetectorMessage;
        detectorWorker.onerror = () => {
            setState("error", "Microphone is not supported.");
        };
        detectorWorker.postMessage({
            type: "init",
            sampleRate: audioContext.sampleRate,
            profileKey: wakeProfileKey,
            enrollmentSampleCount: enrollmentSamples,
            enrollmentDurationMs,
            detectionIntervalMs,
            requiredDetectionStreak,
            thresholdMultiplier,
            preRollMs,
        });
    }

    async function stopAudio() {
        await stopCommandRecognition({ resumeDetector: false });
        if (detectorWorker) {
            detectorWorker.terminate();
            detectorWorker = null;
        }
        detectorReady = false;
        if (audioSource) {
            audioSource.disconnect();
            audioSource = null;
        }
        if (audioProcessor) {
            audioProcessor.disconnect();
            audioProcessor = null;
        }
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        }
        if (audioContext) {
            await audioContext.close();
            audioContext = null;
        }
    }

    async function enableListening() {
        if (!window.Vosk) {
            setState("error", "Microphone is not supported.");
            return;
        }
        const errorMessage = supportError();
        if (errorMessage) {
            setState("error", errorMessage);
            return;
        }
        const currentSession = ++sessionId;
        listeningEnabled = true;
        copilot.setAttribute("aria-pressed", "true");
        copilot.setAttribute("aria-disabled", "false");
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({
                video: false,
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    channelCount: 1,
                },
            });
            audioContext = new AudioContextClass();
            await audioContext.resume();
            if (audioContext.state !== "running") {
                const error = new Error("AudioContext could not be resumed.");
                error.name = "NotAllowedError";
                throw error;
            }
            if (!listeningEnabled || currentSession !== sessionId) {
                await stopAudio();
                return;
            }
            await audioContext.audioWorklet.addModule(workletUrl);
            audioProcessor = new AudioWorkletNode(
                audioContext,
                "adam-audio-processor",
                { channelCount: 1, numberOfInputs: 1, numberOfOutputs: 1 },
            );
            audioProcessor.port.onmessage = forwardAudioToDetector;
            initializeDetector();
            audioSource = audioContext.createMediaStreamSource(mediaStream);
            audioSource.connect(audioProcessor);
            audioProcessor.connect(audioContext.destination);
            saveListeningPreference(true);
            loadOfflineModel().catch(() => {});
        } catch (error) {
            listeningEnabled = false;
            copilot.setAttribute("aria-pressed", "false");
            copilot.setAttribute("aria-disabled", "false");
            await stopAudio();
            if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
                saveListeningPreference(false);
                setState("muted", "Microphone is not active. Click to enable listening.");
            } else {
                saveListeningPreference(false);
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
    document.addEventListener("adam:wake-word", sendTranscription);
    copilot.addEventListener("click", () => {
        if (!listeningEnabled) {
            enableListening();
        } else if (detectorReady && !detectorEnrolled) {
            startEnrollment();
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
