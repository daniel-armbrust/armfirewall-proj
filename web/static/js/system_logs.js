(function () {
    const stateLabel = document.querySelector("#system-logs-state");
    const logsBody = document.querySelector("#system-logs-body");
    const POLL_MS = 5000;
    let loading = false;

    function setState(state, updated = "") {
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

    function levelClass(level) {
        const text = String(level || "").toUpperCase();
        if (text === "ERROR" || text === "FATAL") {
            return "down";
        }
        if (text === "WARNING") {
            return "disabled";
        }
        return "up";
    }

    function renderLogs(rows) {
        if (!logsBody) {
            return;
        }
        if (!rows.length) {
            logsBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no system logs</span></div></td>
                </tr>
            `;
            return;
        }
        logsBody.innerHTML = rows.map((row) => `
            <tr>
                <td>${HF.escapeHtml(row.id)}</td>
                <td>${HF.escapeHtml(row.created_at)}</td>
                <td><span class="status ${levelClass(row.level)}">${HF.escapeHtml(row.level)}</span></td>
                <td>${HF.escapeHtml(row.source)}</td>
                <td>${HF.escapeHtml(row.message)}</td>
            </tr>
        `).join("");
    }

    async function loadLogs() {
        if (loading) {
            return;
        }
        loading = true;
        try {
            setState("Polling");
            const data = await HF.fetchJson("/api/settings/system-logs");
            const summary = data.summary || {};
            setText("#logs-summary-rows", summary.rows);
            setText("#logs-summary-warnings", summary.warnings);
            setText("#logs-summary-errors", summary.errors);
            setText("#logs-summary-last-id", summary.last_id);
            renderLogs(data.logs || []);
            setState("Live", summary.updated_at || "-");
        } catch (error) {
            setState("Offline");
            if (logsBody) {
                logsBody.innerHTML = `
                    <tr>
                        <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
        } finally {
            loading = false;
        }
    }

    loadLogs();
    setInterval(loadLogs, POLL_MS);
}());
