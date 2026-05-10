(function () {
    const stateLabel = document.querySelector("#refresh-state");
    const counterList = document.querySelector("#counter-list");
    const systemUpdated = document.querySelector("#system-updated");

    function setRefreshState(state, updated = "") {
        if (!stateLabel) {
            return;
        }
        if (updated) {
            stateLabel.innerHTML = `${HF.escapeHtml(state)} / <span class="refresh-state-label">updated=</span>${HF.escapeHtml(updated)}`;
            return;
        }

        stateLabel.textContent = state;
    }

    function setText(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            element.textContent = HF.text(value);
        }
    }

    function renderSystemStatus(system) {
        if (!system) {
            return;
        }

        setText("#system-cpu-model", system.cpu_model);
        setText("#system-cpu-count", `cores=${system.cpu_count}`);
        setText("#system-cpu-used", `${system.cpu_usage_percent}%`);
        setText("#system-memory-used", `${system.memory.used_label} (${system.memory.used_percent}%)`);
        setText("#system-memory-total", `total=${system.memory.total_label} available=${system.memory.available_label}`);
        setText("#system-architecture", system.architecture);
        setText("#system-os", system.os);
        setText("#system-processes", system.process_count);
        setText("#system-root-disk", `${system.root_disk.used_label} (${system.root_disk.used_percent}%)`);
        setText("#system-root-disk-free", `free=${system.root_disk.free_label} total=${system.root_disk.total_label}`);

        if (systemUpdated) {
            systemUpdated.textContent = "system=live";
        }
    }

    async function pollTrafficCounters() {
        if (!counterList) {
            return;
        }

        try {
            setRefreshState("Polling");

            const data = await HF.fetchJson("/api/dashboard");
            HF.renderSummary(data.summary);
            HF.renderCounterList(counterList, data.interfaces);
            renderSystemStatus(data.system);

            setRefreshState("Live", data.summary.updated_at || "-");
        } catch (error) {
            setRefreshState("Offline");
            counterList.innerHTML = `<div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>`;
        }
    }

    pollTrafficCounters();
    setInterval(pollTrafficCounters, 5000);
}());
