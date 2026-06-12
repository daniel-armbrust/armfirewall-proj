const TARGET_SAMPLE_RATE = 16000;
const DATABASE_NAME = "armfirewall-adam-wake-word";
const DATABASE_VERSION = 1;
const STORE_NAME = "profiles";

let sampleRate = TARGET_SAMPLE_RATE;
let profileKey = "default";
let enrollmentSampleCount = 5;
let enrollmentDurationMs = 1200;
let detectionIntervalMs = 250;
let requiredDetectionStreak = 3;
let thresholdMultiplier = 1.6;
let preRollMs = 1600;
let templates = [];
let threshold = 0;
let audioBuffer = [];
let enrollmentBuffer = [];
let collectingEnrollment = false;
let detectionPaused = true;
let samplesSinceDetection = 0;
let detectionStreak = 0;
let lastDetectionAt = 0;

function openDatabase() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
        request.onupgradeneeded = () => {
            const database = request.result;
            if (!database.objectStoreNames.contains(STORE_NAME)) {
                database.createObjectStore(STORE_NAME);
            }
        };
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function loadProfile() {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readonly");
        const request = transaction.objectStore(STORE_NAME).get(profileKey);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error);
        transaction.oncomplete = () => database.close();
    });
}

async function saveProfile() {
    const database = await openDatabase();
    return new Promise((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put({ templates, threshold }, profileKey);
        transaction.oncomplete = () => {
            database.close();
            resolve();
        };
        transaction.onerror = () => reject(transaction.error);
    });
}

function resample(input, inputSampleRate) {
    if (inputSampleRate === TARGET_SAMPLE_RATE) {
        return Array.from(input);
    }
    const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
    const outputLength = Math.floor(input.length / ratio);
    const output = new Array(outputLength);
    for (let index = 0; index < outputLength; index += 1) {
        const position = index * ratio;
        const left = Math.floor(position);
        const right = Math.min(left + 1, input.length - 1);
        const fraction = position - left;
        output[index] = input[left] + ((input[right] - input[left]) * fraction);
    }
    return output;
}

function rootMeanSquare(samples) {
    if (!samples.length) {
        return 0;
    }
    let energy = 0;
    for (const sample of samples) {
        energy += sample * sample;
    }
    return Math.sqrt(energy / samples.length);
}

function trimSilence(samples) {
    let maximum = 0;
    for (const sample of samples) {
        maximum = Math.max(maximum, Math.abs(sample));
    }
    const limit = Math.max(0.012, maximum * 0.16);
    let start = 0;
    let end = samples.length - 1;
    while (start < samples.length && Math.abs(samples[start]) < limit) {
        start += 1;
    }
    while (end > start && Math.abs(samples[end]) < limit) {
        end -= 1;
    }
    const padding = Math.floor(TARGET_SAMPLE_RATE * 0.08);
    return samples.slice(Math.max(0, start - padding), Math.min(samples.length, end + padding));
}

function goertzel(frame, frequency) {
    const omega = (2 * Math.PI * frequency) / TARGET_SAMPLE_RATE;
    const coefficient = 2 * Math.cos(omega);
    let previous = 0;
    let previousPrevious = 0;
    for (let index = 0; index < frame.length; index += 1) {
        const window = 0.54 - (0.46 * Math.cos((2 * Math.PI * index) / (frame.length - 1)));
        const current = (frame[index] * window) + (coefficient * previous) - previousPrevious;
        previousPrevious = previous;
        previous = current;
    }
    return Math.log1p(Math.max(0, (previous * previous) + (previousPrevious * previousPrevious)
        - (coefficient * previous * previousPrevious)));
}

function extractFeatures(rawSamples) {
    const samples = trimSilence(rawSamples);
    if (samples.length < TARGET_SAMPLE_RATE * 0.22) {
        return null;
    }
    const frequencies = [250, 375, 550, 800, 1150, 1650, 2300, 3150, 4200, 5500];
    const frameSize = 400;
    const hopSize = 160;
    const frames = [];
    for (let offset = 0; offset + frameSize <= samples.length; offset += hopSize) {
        const frame = samples.slice(offset, offset + frameSize);
        const vector = frequencies.map((frequency) => goertzel(frame, frequency));
        const mean = vector.reduce((sum, value) => sum + value, 0) / vector.length;
        const variance = vector.reduce((sum, value) => sum + ((value - mean) ** 2), 0) / vector.length;
        const deviation = Math.sqrt(variance) || 1;
        frames.push(vector.map((value) => (value - mean) / deviation));
    }
    if (!frames.length) {
        return null;
    }
    const segmentCount = 12;
    return Array.from({ length: segmentCount }, (_, segment) => {
        const start = Math.floor((segment * frames.length) / segmentCount);
        const end = Math.max(start + 1, Math.floor(((segment + 1) * frames.length) / segmentCount));
        const selected = frames.slice(start, Math.min(end, frames.length));
        return frequencies.map((_, feature) => (
            selected.reduce((sum, frame) => sum + frame[feature], 0) / selected.length
        ));
    });
}

function frameDistance(left, right) {
    let sum = 0;
    for (let index = 0; index < left.length; index += 1) {
        sum += (left[index] - right[index]) ** 2;
    }
    return sum / left.length;
}

function sequenceDistance(left, right) {
    const rows = left.length + 1;
    const columns = right.length + 1;
    const matrix = Array.from({ length: rows }, () => Array(columns).fill(Infinity));
    matrix[0][0] = 0;
    for (let row = 1; row < rows; row += 1) {
        for (let column = 1; column < columns; column += 1) {
            const cost = frameDistance(left[row - 1], right[column - 1]);
            matrix[row][column] = cost + Math.min(
                matrix[row - 1][column],
                matrix[row][column - 1],
                matrix[row - 1][column - 1],
            );
        }
    }
    return matrix[left.length][right.length] / (left.length + right.length);
}

function calibrateThreshold() {
    const distances = [];
    for (let left = 0; left < templates.length; left += 1) {
        for (let right = left + 1; right < templates.length; right += 1) {
            distances.push(sequenceDistance(templates[left], templates[right]));
        }
    }
    const maximum = distances.length ? Math.max(...distances) : 0.18;
    return Math.min(0.9, Math.max(0.12, maximum * thresholdMultiplier));
}

async function finishEnrollmentSample() {
    collectingEnrollment = false;
    const captured = enrollmentBuffer.slice();
    enrollmentBuffer = [];
    if (rootMeanSquare(captured) < 0.012) {
        postMessage({ type: "enrollmentTooQuiet" });
        return;
    }
    const features = extractFeatures(captured);
    if (!features) {
        postMessage({ type: "enrollmentTooQuiet" });
        return;
    }
    templates.push(features);
    postMessage({ type: "enrollmentSampleComplete", count: templates.length });
    if (templates.length >= enrollmentSampleCount) {
        threshold = calibrateThreshold();
        await saveProfile();
        detectionPaused = false;
        postMessage({ type: "enrollmentComplete", threshold });
    }
}

function detectWakeWord() {
    if (detectionPaused || templates.length < enrollmentSampleCount) {
        return;
    }
    const now = Date.now();
    if (now - lastDetectionAt < 3000 || rootMeanSquare(audioBuffer) < 0.01) {
        return;
    }
    const features = extractFeatures(audioBuffer);
    if (!features) {
        return;
    }
    const distance = Math.min(...templates.map((template) => sequenceDistance(features, template)));
    const matched = distance <= threshold;
    detectionStreak = matched ? detectionStreak + 1 : 0;
    postMessage({ type: "score", score: Math.max(0, 1 - (distance / threshold)), distance, threshold });
    if (detectionStreak < requiredDetectionStreak) {
        return;
    }
    detectionStreak = 0;
    detectionPaused = true;
    lastDetectionAt = now;
    const preRoll = new Float32Array(audioBuffer);
    postMessage(
        { type: "wakeWord", score: Math.max(0, 1 - (distance / threshold)), preRoll },
        [preRoll.buffer],
    );
}

function receiveAudio(data, inputSampleRate) {
    const samples = resample(data, inputSampleRate);
    const maximumSamples = Math.floor((preRollMs / 1000) * TARGET_SAMPLE_RATE);
    audioBuffer.push(...samples);
    if (audioBuffer.length > maximumSamples) {
        audioBuffer.splice(0, audioBuffer.length - maximumSamples);
    }
    if (collectingEnrollment) {
        enrollmentBuffer.push(...samples);
        const required = Math.floor((enrollmentDurationMs / 1000) * TARGET_SAMPLE_RATE);
        if (enrollmentBuffer.length >= required) {
            finishEnrollmentSample().catch((error) => postMessage({ type: "error", error: error.message }));
        }
        return;
    }
    samplesSinceDetection += samples.length;
    if (samplesSinceDetection >= (detectionIntervalMs / 1000) * TARGET_SAMPLE_RATE) {
        samplesSinceDetection = 0;
        detectWakeWord();
    }
}

self.onmessage = async (event) => {
    const message = event.data;
    try {
        if (message.type === "init") {
            sampleRate = message.sampleRate || TARGET_SAMPLE_RATE;
            profileKey = message.profileKey || profileKey;
            enrollmentSampleCount = message.enrollmentSampleCount || enrollmentSampleCount;
            enrollmentDurationMs = message.enrollmentDurationMs || enrollmentDurationMs;
            detectionIntervalMs = message.detectionIntervalMs || detectionIntervalMs;
            requiredDetectionStreak = message.requiredDetectionStreak || requiredDetectionStreak;
            thresholdMultiplier = message.thresholdMultiplier || thresholdMultiplier;
            preRollMs = message.preRollMs || preRollMs;
            const profile = await loadProfile();
            if (profile) {
                templates = profile.templates || [];
                threshold = profile.threshold || calibrateThreshold();
                detectionPaused = false;
            }
            postMessage({ type: "ready", enrolled: templates.length >= enrollmentSampleCount });
        } else if (message.type === "audio") {
            receiveAudio(message.data, message.sampleRate || sampleRate);
        } else if (message.type === "startEnrollment") {
            templates = [];
            threshold = 0;
            audioBuffer = [];
            detectionPaused = true;
            collectingEnrollment = false;
            postMessage({ type: "enrollmentReady" });
        } else if (message.type === "recordEnrollmentSample") {
            enrollmentBuffer = [];
            collectingEnrollment = true;
        } else if (message.type === "resumeDetection") {
            audioBuffer = [];
            detectionPaused = false;
        }
    } catch (error) {
        postMessage({ type: "error", error: error.message });
    }
};
