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
    const commandSilenceThreshold = Number.parseFloat(copilot.dataset.commandSilenceThreshold) || 0.004;
    const commandTimeoutMs = Number.parseInt(copilot.dataset.commandTimeoutMs, 10) || 8000;
    const commandTrailingSilenceMs = Number.parseInt(
        copilot.dataset.commandTrailingSilenceMs,
        10,
    ) || 900;
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    const debugLog = () => {};
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
    let enrollmentRecognizer = null;
    let enrollmentRecognizerChannel = null;
    let enrollmentResultSegments = [];
    let enrollmentPartialTranscript = "";
    let enrollmentFinalizationTimer = null;
    let pendingEnrollmentStart = false;
    let serverWakeProfile = null;
    let recognizer = null;
    let recognizerChannel = null;
    let commandTimeout = null;
    let commandSilenceTimer = null;
    let commandFinalizeTimer = null;
    let commandStartedAt = 0;
    let commandSpeechDetected = false;
    let commandResultSegments = [];
    let commandPartialTranscript = "";
    let recognizerRemovalRequested = false;
    let commandConfidence = 0;
    let listeningEnabled = false;
    let commandRecognitionActive = false;
    let sessionId = 0;
    let adamWebSocket = null;
    let socketReconnectTimer = null;
    let socketHeartbeatTimer = null;
    let pageIsClosing = false;
    let adamDisabled = false;

    function websocketUrl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        return `${protocol}//${window.location.host}/ws/adam`;
    }

    function createRequestId() {
        if (window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
            const random = Math.floor(Math.random() * 16);
            const value = character === "x" ? random : (random & 0x3) | 0x8;
            return value.toString(16);
        });
    }

    function clearWebSocketTimers() {
        window.clearTimeout(socketReconnectTimer);
        window.clearInterval(socketHeartbeatTimer);
        socketReconnectTimer = null;
        socketHeartbeatTimer = null;
    }

    function closeAdamWebSocket() {
        clearWebSocketTimers();
        if (adamWebSocket) {
            adamWebSocket.close();
            adamWebSocket = null;
        }
    }

    function scheduleWebSocketReconnect() {
        if (pageIsClosing || adamDisabled || socketReconnectTimer) {
            return;
        }
        socketReconnectTimer = window.setTimeout(() => {
            socketReconnectTimer = null;
            connectAdamWebSocket();
        }, 3000);
    }

    function connectAdamWebSocket() {
        if (pageIsClosing || adamDisabled || (adamWebSocket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(adamWebSocket.readyState))) {
            return;
        }
        const socket = new WebSocket(websocketUrl());
        adamWebSocket = socket;
        socket.addEventListener("open", () => {
            debugLog("ADAM WebSocket connected");
            socketHeartbeatTimer = window.setInterval(() => {
                if (socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({type: "session.ping"}));
                }
            }, 25000);
        });
        socket.addEventListener("message", (event) => {
            try {
                const message = JSON.parse(event.data);
                debugLog("ADAM WebSocket event", message.type, message.request_id || "");
            } catch (_error) {
                debugLog("ADAM WebSocket returned an invalid event");
            }
        });
        socket.addEventListener("close", (event) => {
            if (adamWebSocket === socket) {
                adamWebSocket = null;
            }
            window.clearInterval(socketHeartbeatTimer);
            socketHeartbeatTimer = null;
            if (event.code === 4403) {
                adamDisabled = true;
                debugLog("ADAM WebSocket closed because ADAM is disabled");
                return;
            }
            scheduleWebSocketReconnect();
        });
        socket.addEventListener("error", () => {
            debugLog("ADAM WebSocket connection failed");
        });
    }

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

    async function loadServerWakeWordProfile() {
        const response = await window.fetch(
            `/api/adam/wake-word?profile_key=${encodeURIComponent(wakeProfileKey)}`,
            { cache: "no-store", credentials: "same-origin", headers: { Accept: "application/json" } },
        );
        if (!response.ok) {
            throw new Error("Unable to load the wake-word profile.");
        }
        const payload = await response.json();
        return payload.profile || null;
    }

    async function saveServerWakeWordProfile(profile) {
        const response = await window.fetch("/api/adam/wake-word", {
            method: "PUT",
            credentials: "same-origin",
            headers: { Accept: "application/json", "Content-Type": "application/json" },
            body: JSON.stringify({
                profile_key: wakeProfileKey,
                templates: profile.templates,
                threshold: profile.threshold,
            }),
        });
        if (!response.ok) {
            throw new Error("Unable to save the wake-word profile.");
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
        setState("muted", "Wake word setup required.");
        copilot.setAttribute("aria-disabled", "false");
        publishWakeWordStatus("required", "Wake word setup required.");
    }

    function publishWakeWordStatus(state, message, extra = {}) {
        document.dispatchEvent(new CustomEvent("adam:wake-word-status", {
            detail: {
                state,
                message,
                enrolled: detectorEnrolled,
                completedSamples: enrollmentCompletedSamples,
                requiredSamples: enrollmentSamples,
                ...extra,
            },
        }));
    }

    function setWakeAlertState({ autoTransition = true } = {}) {
        window.clearTimeout(wakeAlertTimer);
        copilot.dataset.state = "wake-alert";
        copilot.setAttribute(
            "aria-label",
            "Adam: wake word detected; listening for command",
        );
        if (status) {
            status.textContent = "!";
        }
        if (autoTransition) {
            wakeAlertTimer = window.setTimeout(() => {
                wakeAlertTimer = null;
                if (copilot.dataset.state === "wake-alert") {
                    setSilentState("command", "listening for command");
                }
            }, 1200);
        }
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
        if (!recognizer) {
            debugLog("command capture ended without an active recognizer");
            stopCommandRecognition();
            return;
        }
        debugLog("command capture finishing", {
            speechDetected: commandSpeechDetected,
            finalSegments: commandResultSegments.length,
            partial: commandPartialTranscript,
        });
        recognizerRemovalRequested = true;
        if (audioProcessor) {
            audioProcessor.port.postMessage({ action: "stopRecognizer" });
        }
        // Give Vosk time to emit the final result before freeing the recognizer.
        // This is important when Firefox delivers the last audio chunk slightly
        // later than Chromium-based browsers.
        commandFinalizeTimer = window.setTimeout(() => {
            commandFinalizeTimer = null;
            if (!commandRecognitionActive) {
                return;
            }
            if (recognizer) {
                recognizer.remove();
            }
            const transcript = (commandResultSegments.join(" ").trim() || commandPartialTranscript).trim();
            const command = commandAfterWakeWord(transcript);
            debugLog("command capture finalized", { transcript, command });
            if (command) {
                acceptCommand(transcript, command);
            } else {
                stopCommandRecognition();
            }
        }, 1000);
    }

    function enrollmentTranscriptIsValid(transcript) {
        const normalizedTranscript = normalizeText(transcript)
            .replace(/[^a-z0-9\s]/g, "")
            .replace(/\s+/g, " ")
            .trim();
        const normalizedWakeWord = normalizeText(wakeWord);
        return normalizedTranscript === normalizedWakeWord;
    }

    async function beginEnrollmentSample(sampleNumber) {
        const model = await loadOfflineModel();
        if (!enrollmentInProgress || !audioProcessor || !detectorWorker) {
            return;
        }
        enrollmentResultSegments = [];
        enrollmentPartialTranscript = "";
        enrollmentRecognizerChannel = new MessageChannel();
        model.registerPort(enrollmentRecognizerChannel.port1);
        enrollmentRecognizer = new model.KaldiRecognizer(commandSampleRate);
        const activeRecognizer = enrollmentRecognizer;
        enrollmentRecognizer.on("result", (result) => {
            if (enrollmentRecognizer === activeRecognizer) {
                const text = (result.result.text || "").trim();
                if (text && enrollmentResultSegments.at(-1) !== text) {
                    enrollmentResultSegments.push(text);
                }
            }
        });
        enrollmentRecognizer.on("partialresult", (result) => {
            if (enrollmentRecognizer === activeRecognizer) {
                enrollmentPartialTranscript = (result.result.partial || "").trim();
            }
        });
        audioProcessor.port.postMessage({
            action: "startRecognizer",
            recognizerId: enrollmentRecognizer.id,
            sampleRate: commandSampleRate,
        }, [enrollmentRecognizerChannel.port2]);
        detectorWorker.postMessage({ type: "recordEnrollmentSample" });
        publishWakeWordStatus("recording", `Say “${spokenWakeWord}” now.`, {sampleNumber});
    }

    function scheduleEnrollmentSample(sampleNumber, delay = 700) {
        if (!enrollmentInProgress || !detectorWorker) {
            return;
        }
        setState(
            "awake",
            `Get ready for wake word sample ${sampleNumber}/${enrollmentSamples}.`,
        );
        window.setTimeout(() => {
            if (enrollmentInProgress && detectorWorker) {
                beginEnrollmentSample(sampleNumber).catch(() => {
                    enrollmentInProgress = false;
                    setState("error", "Unable to verify the wake word.");
                    publishWakeWordStatus("error", "Unable to verify the wake word.");
                });
            }
        }, delay);
    }

    function startEnrollment({replace = false} = {}) {
        if (!detectorReady || (!replace && detectorEnrolled) || enrollmentInProgress || !detectorWorker) {
            return;
        }
        enrollmentInProgress = true;
        enrollmentCompletedSamples = 0;
        copilot.setAttribute("aria-disabled", "true");
        detectorWorker.postMessage({ type: "startEnrollment" });
        publishWakeWordStatus("starting", "Preparing wake word setup.");
    }

    function finishEnrollmentRecognition() {
        if (!enrollmentRecognizer || !audioProcessor || !detectorWorker) {
            return;
        }
        audioProcessor.port.postMessage({ action: "stopRecognizer" });
        window.clearTimeout(enrollmentFinalizationTimer);
        enrollmentFinalizationTimer = window.setTimeout(() => {
            const transcript = (
                enrollmentResultSegments.join(" ").trim() || enrollmentPartialTranscript
            ).trim();
            enrollmentRecognizer.remove();
            enrollmentRecognizer = null;
            if (enrollmentRecognizerChannel) {
                enrollmentRecognizerChannel.port1.close();
                enrollmentRecognizerChannel = null;
            }
            if (enrollmentTranscriptIsValid(transcript)) {
                detectorWorker.postMessage({ type: "acceptEnrollmentSample" });
                return;
            }
            detectorWorker.postMessage({ type: "rejectEnrollmentSample" });
            setState("retry", `Only “${spokenWakeWord}” is valid. Please try again.`);
            publishWakeWordStatus("invalid", `Only “${spokenWakeWord}” is valid. Please try again.`);
        }, 450);
    }

    function discardEnrollmentRecognition() {
        window.clearTimeout(enrollmentFinalizationTimer);
        enrollmentFinalizationTimer = null;
        if (audioProcessor) {
            audioProcessor.port.postMessage({ action: "stopRecognizer" });
        }
        if (enrollmentRecognizer) {
            enrollmentRecognizer.remove();
            enrollmentRecognizer = null;
        }
        if (enrollmentRecognizerChannel) {
            enrollmentRecognizerChannel.port1.close();
            enrollmentRecognizerChannel = null;
        }
        enrollmentResultSegments = [];
        enrollmentPartialTranscript = "";
    }

    async function stopCommandRecognition({ resumeDetector = true } = {}) {
        window.clearTimeout(commandTimeout);
        window.clearTimeout(commandSilenceTimer);
        window.clearTimeout(commandFinalizeTimer);
        commandTimeout = null;
        commandSilenceTimer = null;
        commandFinalizeTimer = null;
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
        commandPartialTranscript = "";
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
            debugLog("transcription skipped because the command is empty", event.detail);
            return;
        }
        debugLog("sending transcription", { text, language: speechLanguage });
        if (adamWebSocket && adamWebSocket.readyState === WebSocket.OPEN) {
            const requestId = createRequestId();
            adamWebSocket.send(JSON.stringify({
                type: "command.submit",
                request_id: requestId,
                text,
                language: speechLanguage,
            }));
            return;
        }
        try {
            const response = await window.fetch("/api/adam/transcription", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text, language: speechLanguage }),
            });
            debugLog("transcription response", response.status);
        } catch {
            debugLog("transcription request failed");
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
            debugLog("Vosk final result", segment);
        }
        if (!recognizerRemovalRequested) {
            return;
        }
        const transcript = (commandResultSegments.join(" ").trim() || commandPartialTranscript).trim();
        if (!transcript) {
            stopCommandRecognition();
            return;
        }
        const command = commandAfterWakeWord(transcript);
        if (command) {
            acceptCommand(transcript, command);
        }
    }

    function processCommandPartialResult(message) {
        if (!commandRecognitionActive
            || !recognizer
            || message.recognizerId !== recognizer.id) {
            return;
        }
        commandPartialTranscript = (message.result.partial || "").trim();
        if (commandPartialTranscript) {
            debugLog("Vosk partial result", commandPartialTranscript);
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
        commandPartialTranscript = "";
        recognizerRemovalRequested = false;
        debugLog("starting command recognizer", {
            wakeScore: message.score,
            sampleRate: commandSampleRate,
            preRollSamples: message.preRoll ? message.preRoll.length : 0,
        });
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
            debugLog("command recognizer ready", { recognizerId: recognizer.id });
            const activeRecognizer = recognizer;
            recognizer.on("result", (result) => {
                if (recognizer === activeRecognizer) {
                    processCommandResult(result);
                }
            });
            recognizer.on("partialresult", (result) => {
                if (recognizer === activeRecognizer) {
                    processCommandPartialResult(result);
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
            debugLog("command recognizer failed to start");
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
                publishWakeWordStatus("ready", "Wake word is ready.");
            } else {
                setEnrollmentPrompt();
            }
            if (pendingEnrollmentStart) {
                pendingEnrollmentStart = false;
                startEnrollment({replace: true});
            }
        } else if (message.type === "enrollmentReady") {
            scheduleEnrollmentSample(1);
        } else if (message.type === "enrollmentSampleCaptured") {
            finishEnrollmentRecognition();
        } else if (message.type === "enrollmentSampleComplete") {
            enrollmentCompletedSamples = message.count;
            publishWakeWordStatus(
                "progress",
                `Wake word sample ${message.count}/${enrollmentSamples} saved.`,
            );
            if (message.count < enrollmentSamples) {
                scheduleEnrollmentSample(message.count + 1, 900);
            }
        } else if (message.type === "enrollmentSampleRejected") {
            const nextSample = Math.min(enrollmentSamples, enrollmentCompletedSamples + 1);
            scheduleEnrollmentSample(nextSample, 1200);
        } else if (message.type === "enrollmentTooQuiet") {
            discardEnrollmentRecognition();
            setState("retry", `I couldn't hear you. Say “${spokenWakeWord}” again.`);
            const nextSample = Math.min(enrollmentSamples, enrollmentCompletedSamples + 1);
            scheduleEnrollmentSample(nextSample, 1200);
        } else if (message.type === "enrollmentComplete") {
            enrollmentInProgress = false;
            detectorEnrolled = true;
            serverWakeProfile = message.profile || null;
            setListeningState();
            publishWakeWordStatus("complete", "Wake word setup completed.");
            if (serverWakeProfile) {
                saveServerWakeWordProfile(serverWakeProfile).catch(() => {
                    publishWakeWordStatus("error", "Wake word was trained, but could not be saved.");
                });
            }
        } else if (message.type === "enrollmentCancelled") {
            discardEnrollmentRecognition();
            enrollmentInProgress = false;
            setEnrollmentPrompt();
        } else if (message.type === "wakeWord") {
            debugLog("wake word detected", {
                score: message.score,
                threshold: minConfidence,
            });
            // Show the visual confirmation for every detector event, even when
            // the confidence gate rejects it as a command trigger.
            setWakeAlertState({ autoTransition: message.score >= minConfidence });
            if (message.score >= minConfidence) {
                startCommandRecognition(message);
            } else if (detectorWorker) {
                window.setTimeout(() => {
                    if (detectorWorker && !commandRecognitionActive) {
                        detectorWorker.postMessage({ type: "resumeDetection" });
                        setListeningState();
                    }
                }, 1200);
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
            profile: serverWakeProfile,
        });
    }

    async function stopAudio() {
        await stopCommandRecognition({ resumeDetector: false });
        window.clearTimeout(enrollmentFinalizationTimer);
        enrollmentFinalizationTimer = null;
        if (enrollmentRecognizer) {
            enrollmentRecognizer.remove();
            enrollmentRecognizer = null;
        }
        if (enrollmentRecognizerChannel) {
            enrollmentRecognizerChannel.port1.close();
            enrollmentRecognizerChannel = null;
        }
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

    async function enableListening({enrollWakeWord = false} = {}) {
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
            if (enrollWakeWord) {
                pendingEnrollmentStart = true;
            }
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
    document.addEventListener("adam:wake-word:status:request", () => {
        publishWakeWordStatus(
            detectorEnrolled ? "ready" : "required",
            detectorEnrolled ? "Wake word is ready." : "Wake word setup required.",
        );
    });
    document.addEventListener("adam:wake-word:enroll", () => {
        if (listeningEnabled && detectorReady) {
            startEnrollment({replace: true});
            return;
        }
        pendingEnrollmentStart = true;
        enableListening({enrollWakeWord: true});
    });
    document.addEventListener("adam:wake-word:cancel", () => {
        if (detectorWorker && enrollmentInProgress) {
            discardEnrollmentRecognition();
            detectorWorker.postMessage({ type: "cancelEnrollment" });
        }
    });
    copilot.addEventListener("click", () => {
        if (!listeningEnabled) {
            if (!detectorEnrolled) {
                window.location.assign("/armfirewall/adam#wake-word");
                return;
            }
            enableListening();
        } else if (detectorReady && !detectorEnrolled) {
            startEnrollment();
        }
    });

    if (logoutLink) {
        logoutLink.addEventListener("click", (event) => {
            event.preventDefault();
            pageIsClosing = true;
            closeAdamWebSocket();
            listeningEnabled = false;
            sessionId += 1;
            stopAudio().finally(() => {
                clearListeningPreference();
                window.location.assign(logoutLink.href);
            });
        }, { once: true });
    }

    const savedListeningPreference = listeningPreference();
    connectAdamWebSocket();
    loadServerWakeWordProfile().then((profile) => {
        serverWakeProfile = profile;
        detectorEnrolled = Boolean(profile && profile.templates
            && profile.templates.length >= enrollmentSamples);
        if (!detectorEnrolled) {
            setEnrollmentPrompt();
            return;
        }
        publishWakeWordStatus("ready", "Wake word is ready.");
        if (savedListeningPreference === "true") {
            enableListening();
        } else {
            setState("muted", "Microphone is not active. Click to enable listening.");
        }
    }).catch(() => {
        detectorEnrolled = false;
        setEnrollmentPrompt();
    });

    window.addEventListener("pagehide", () => {
        pageIsClosing = true;
        closeAdamWebSocket();
        listeningEnabled = false;
        sessionId += 1;
        stopAudio();
        if (modelPromise) {
            modelPromise.then((model) => model.terminate()).catch(() => {});
        }
    });
})();
