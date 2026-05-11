(function () {
    const state = document.getElementById("traceroute-state");
    const form = document.getElementById("traceroute-form");
    const ifaceSelect = document.getElementById("traceroute-iface");
    const status = document.getElementById("traceroute-form-status");
    const commandLabel = document.getElementById("traceroute-command");
    const output = document.getElementById("traceroute-output");
    const clearButton = document.getElementById("traceroute-clear");
    const runButton = form ? form.querySelector('button[type="submit"]') : null;
    let isRunning = false;

    function setState(value) {
        if (state) {
            state.textContent = value;
        }
    }

    function setStatus(message, isError = false) {
        if (!status) {
            return;
        }
        status.textContent = message || "";
        status.classList.toggle("error", Boolean(isError));
    }

    function setRunning(value) {
        isRunning = Boolean(value);
        if (runButton) {
            runButton.disabled = isRunning;
            runButton.textContent = isRunning ? "Running" : "Run";
        }
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            cache: "no-store",
            credentials: "same-origin",
            headers: {
                "Accept": "application/json",
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
            ...options,
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return null;
        }
        if (response.status === 403) {
            window.location.href = "/login/change-password";
            return null;
        }

        const text = await response.text();
        let payload = {};
        if (text) {
            try {
                payload = JSON.parse(text);
            } catch (error) {
                payload = { detail: text.trim() || "Invalid server response." };
            }
        }
        if (!response.ok) {
            throw new Error(payload.detail || `HTTP ${response.status}`);
        }
        return payload;
    }

    function interfaceLabel(iface) {
        const role = iface.role || "UNKNOWN";
        const description = iface.description || "-";
        return `${iface.name} (${role}) - ${description}`;
    }

    function renderInterfaces(interfaces) {
        if (!ifaceSelect) {
            return;
        }
        ifaceSelect.innerHTML = '<option value="">auto</option>';
        (interfaces || []).forEach((iface) => {
            const option = document.createElement("option");
            option.value = iface.name;
            option.textContent = interfaceLabel(iface);
            ifaceSelect.appendChild(option);
        });
    }

    async function loadContext() {
        try {
            const data = await requestJson("/api/tools/traceroute");
            if (!data) {
                return;
            }
            renderInterfaces(data.interfaces || []);
            setState("Ready");
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
        }
    }

    function formPayload() {
        return {
            target: form.elements.target.value,
            iface: form.elements.iface.value,
            family: form.elements.family.value,
            protocol: form.elements.protocol.value,
            max_hops: Number(form.elements.max_hops.value || 30),
            timeout: Number(form.elements.timeout.value || 3),
            probes: Number(form.elements.probes.value || 3),
        };
    }

    function appendOutput(line) {
        if (!output) {
            return;
        }
        output.textContent += `${line}\n`;
        output.scrollTop = output.scrollHeight;
    }

    function clearOutput() {
        if (isRunning) {
            return;
        }
        if (form) {
            form.reset();
        }
        setStatus("");
        setState("Ready");
        if (commandLabel) {
            commandLabel.textContent = "command=-";
        }
        if (output) {
            output.textContent = "Waiting for execution.";
        }
        if (form && form.elements.target) {
            form.elements.target.focus();
        }
    }

    function handleStreamEvent(eventName, payload) {
        if (eventName === "start") {
            if (commandLabel) {
                commandLabel.textContent = `command=${payload.command || "-"}`;
            }
            appendOutput(`$ ${payload.command || "traceroute"}`);
            return;
        }
        if (eventName === "line") {
            appendOutput(payload.line || "");
            return;
        }
        if (eventName === "busy") {
            setState("Busy");
            setStatus(payload.message || "Traceroute is already running.", true);
            if (output) {
                output.textContent = payload.message || "Traceroute is already running.";
            }
            return;
        }
        if (eventName === "done") {
            setState(payload.ok ? "Success" : `Failed ${payload.returncode}`);
            setRunning(false);
        }
    }

    function processSseBuffer(buffer, flush = false) {
        const events = [];
        let boundary = buffer.indexOf("\n\n");

        while (boundary !== -1) {
            events.push(buffer.slice(0, boundary));
            buffer = buffer.slice(boundary + 2);
            boundary = buffer.indexOf("\n\n");
        }

        if (flush && buffer.trim()) {
            events.push(buffer);
            buffer = "";
        }

        events.forEach((eventBlock) => {
            let eventName = "message";
            const dataLines = [];
            eventBlock.split("\n").forEach((line) => {
                if (line.startsWith("event:")) {
                    eventName = line.slice(6).trim();
                } else if (line.startsWith("data:")) {
                    dataLines.push(line.slice(5).trimStart());
                }
            });
            if (!dataLines.length) {
                return;
            }
            try {
                handleStreamEvent(eventName, JSON.parse(dataLines.join("\n")));
            } catch (error) {
                appendOutput(dataLines.join("\n"));
            }
        });

        return buffer;
    }

    async function runTraceroute(event) {
        event.preventDefault();
        if (isRunning) {
            return;
        }
        setRunning(true);
        setState("Running");
        setStatus("");
        if (output) {
            output.textContent = "";
        }
        if (commandLabel) {
            commandLabel.textContent = "command=running";
        }

        try {
            const response = await fetch("/api/tools/traceroute/stream", {
                method: "POST",
                cache: "no-store",
                credentials: "same-origin",
                headers: {
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(formPayload()),
            });

            if (response.status === 401) {
                window.location.href = "/login";
                return;
            }
            if (response.status === 403) {
                window.location.href = "/login/change-password";
                return;
            }
            if (!response.ok) {
                const text = await response.text();
                let detail = text || `HTTP ${response.status}`;
                try {
                    detail = JSON.parse(text).detail || detail;
                } catch (error) {
                    // Keep the plain response text.
                }
                throw new Error(detail);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) {
                    break;
                }
                buffer += decoder.decode(value, { stream: true });
                buffer = processSseBuffer(buffer);
            }

            buffer += decoder.decode();
            processSseBuffer(buffer, true);
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
            if (output) {
                output.textContent = error.message;
            }
        } finally {
            setRunning(false);
        }
    }

    if (form) {
        form.addEventListener("submit", runTraceroute);
    }
    if (clearButton) {
        clearButton.addEventListener("click", clearOutput);
    }
    loadContext();
}());
