(function () {
    const stateLabel = document.querySelector("#kernel-params-state");
    const paramsList = document.querySelector("#kernel-params-list");
    const countLabel = document.querySelector("#kernel-params-count");
    const modal = document.querySelector("#kernel-param-modal");
    const form = document.querySelector("#kernel-param-form");
    const pathField = document.querySelector("#kernel-param-path");
    const valueField = document.querySelector("#kernel-param-value");
    const statusLabel = document.querySelector("#kernel-param-status");
    const POLL_MS = 10000;

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

    function groupByCategory(rows) {
        return rows.reduce((groups, row) => {
            const category = HF.text(row.category || "Kernel");
            groups[category] = groups[category] || [];
            groups[category].push(row);
            return groups;
        }, {});
    }

    function renderCategoryTable(category, rows) {
        return `
            <section class="proc-family">
                <h3>${HF.escapeHtml(category)}</h3>
                <div class="table-wrap">
                    <table class="data-table proc-table">
                        <thead>
                            <tr>
                                <th>PATH</th>
                                <th>Description</th>
                                <th>Default</th>
                                <th>Current</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.map((row) => `
                                <tr>
                                    <td><code class="proc-path">${HF.escapeHtml(row.proc_path)}</code></td>
                                    <td>${HF.escapeHtml(row.description)}</td>
                                    <td>${HF.escapeHtml(row.default_value)}</td>
                                    <td><span class="proc-value-cell">${HF.escapeHtml(row.current_value)}</span></td>
                                    <td>
                                        <button
                                            class="text-button compact"
                                            type="button"
                                            data-kernel-param-edit
                                            data-proc-path="${HF.escapeHtml(row.proc_path)}"
                                            data-current-value="${HF.escapeHtml(row.current_value)}"
                                            ${HF.number(row.available) === 1 ? "" : "disabled"}
                                        >Edit</button>
                                    </td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
            </section>
        `;
    }

    function renderParams(rows) {
        if (!paramsList) {
            return;
        }
        if (countLabel) {
            countLabel.textContent = `items=${HF.number(rows.length).toLocaleString()}`;
        }
        if (!rows.length) {
            paramsList.innerHTML = `<div class="terminal-empty"><span class="prompt">$</span><span>no global kernel params</span></div>`;
            return;
        }

        const grouped = groupByCategory(rows);
        paramsList.innerHTML = Object.keys(grouped)
            .sort()
            .map((category) => renderCategoryTable(category, grouped[category]))
            .join("");
    }

    async function loadKernelParams() {
        try {
            setState("Polling");
            const data = await HF.fetchJson("/api/network/kernel-params");
            const summary = data.summary || {};
            setText("#kernel-summary-items", HF.number(summary.items).toLocaleString());
            setText("#kernel-summary-available", HF.number(summary.available).toLocaleString());
            setText("#kernel-summary-enabled", HF.number(summary.enabled).toLocaleString());
            setText("#kernel-summary-missing", HF.number(summary.missing).toLocaleString());
            renderParams(data.params || []);
            setState("Live", summary.updated_at || "-");
        } catch (error) {
            setState("Offline");
            if (paramsList) {
                paramsList.innerHTML = `<div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>`;
            }
        }
    }

    function openModal(procPath, currentValue) {
        if (!modal || !pathField || !valueField) {
            return;
        }
        pathField.value = procPath;
        valueField.value = currentValue;
        if (statusLabel) {
            statusLabel.textContent = "";
        }
        modal.hidden = false;
        valueField.focus();
    }

    function closeModal() {
        if (modal) {
            modal.hidden = true;
        }
    }

    document.addEventListener("click", (event) => {
        const editButton = event.target.closest("[data-kernel-param-edit]");
        if (editButton) {
            openModal(editButton.dataset.procPath, editButton.dataset.currentValue);
            return;
        }
        if (event.target.id === "kernel-param-close" || event.target.id === "kernel-param-cancel" || event.target === modal) {
            closeModal();
        }
    });

    window.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeModal();
        }
    });

    if (form) {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (!pathField || !valueField) {
                return;
            }
            if (statusLabel) {
                statusLabel.textContent = "saving";
            }
            try {
                await HF.fetchJson("/api/network/kernel-params/current-value", {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        proc_path: pathField.value,
                        current_value: valueField.value.trim(),
                    }),
                });
                closeModal();
                await loadKernelParams();
            } catch (error) {
                if (statusLabel) {
                    statusLabel.textContent = error.message;
                }
            }
        });
    }

    loadKernelParams();
    setInterval(loadKernelParams, POLL_MS);
}());
