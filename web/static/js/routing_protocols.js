(function () {
    const birdState = document.querySelector("#routing-bird-state");
    const birdVersion = document.querySelector("#routing-bird-version");
    const birdPid = document.querySelector("#routing-bird-pid");
    const birdUptime = document.querySelector("#routing-bird-uptime");
    const form = document.querySelector("#bird-global-settings-form");
    const status = document.querySelector("#bird-global-settings-status");
    const actionModal = document.querySelector("#bird-action-modal");
    const actionTitle = document.querySelector("#bird-action-title");
    const actionMessage = document.querySelector("#bird-action-message");
    const actionConfirm = document.querySelector("[data-bird-modal-confirm]");
    const workRequestsPanel = document.querySelector("#bird-work-requests-panel");
    const workRequestsBody = document.querySelector("#bird-work-requests-body");
    const workRequestsCount = document.querySelector("#bird-work-requests-count");
    const daemonSettingsPanel = document.querySelector("#bird-daemon-settings-panel");
    const viewButtons = Array.from(document.querySelectorAll("[data-routing-view]"));
    const panels = {
        "global-config": document.querySelector("#routing-global-config-panel"),
        rip: document.querySelector("#routing-rip-panel"),
        ospf: document.querySelector("#routing-ospf-panel"),
        bgp: document.querySelector("#routing-bgp-panel"),
        "work-requests": workRequestsPanel,
    };

    const fields = {
        router_id: document.querySelector("#bird-router-id"),
        device_scan_time: document.querySelector("#bird-device-scan-time"),
        kernel_scan_time: document.querySelector("#bird-kernel-scan-time"),
        kernel_learn: document.querySelector("#bird-kernel-learn"),
        kernel_persist: document.querySelector("#bird-kernel-persist"),
        kernel_import: document.querySelector("#bird-kernel-import"),
        kernel_export: document.querySelector("#bird-kernel-export"),
    };
    let currentServiceState = "";
    let pendingAction = null;
    let workRequestsLoading = false;

    function setText(element, value) {
        if (element) {
            element.textContent = HF.text(value);
        }
    }

    function setStatus(message, isError) {
        if (!status) {
            return;
        }
        status.textContent = message;
        status.hidden = !message;
        status.classList.toggle("error", Boolean(isError));
    }

    function setActiveView(viewName) {
        const selectedView = panels[viewName] ? viewName : "global-config";
        Object.entries(panels).forEach(([name, panel]) => {
            if (panel) {
                panel.hidden = name !== selectedView;
            }
        });
        viewButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.routingView === selectedView);
        });
        if (selectedView === "work-requests") {
            loadWorkRequests();
        }
    }

    function closeActionModal() {
        if (actionModal) {
            actionModal.hidden = true;
        }
        pendingAction = null;
        if (actionConfirm) {
            actionConfirm.disabled = false;
        }
    }

    function openActionModal(action, label, run) {
        pendingAction = {action, run};
        if (actionTitle) {
            actionTitle.textContent = "Confirm action";
        }
        if (actionMessage) {
            actionMessage.textContent = label;
        }
        if (actionConfirm) {
            actionConfirm.disabled = false;
        }
        if (actionModal) {
            actionModal.hidden = false;
        }
    }

    function populateForm(settings) {
        Object.entries(fields).forEach(([name, element]) => {
            if (!element) {
                return;
            }
            if (element.type === "checkbox") {
                element.checked = Boolean(settings[name]);
            } else {
                element.value = settings[name] === undefined || settings[name] === null ? "" : String(settings[name]);
            }
        });
    }

    function readForm() {
        const payload = {};
        Object.entries(fields).forEach(([name, element]) => {
            if (!element) {
                return;
            }
            payload[name] = element.type === "checkbox" ? element.checked : element.value;
        });
        return payload;
    }

    function render(data) {
        const service = data.service || {};
        const settings = data.settings || {};
        const installed = Boolean(service.installed);
        const state = installed ? service.state : "NOT INSTALLED";
        currentServiceState = String(service.state || "").toUpperCase();

        setText(birdState, state);
        setText(birdVersion, data.bird_version || "-");
        setText(birdPid, installed ? service.pid : "-");
        setText(birdUptime, installed ? service.uptime : "-");
        populateForm(settings);
    }

    async function load() {
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/global-settings");
            render(data);
        } catch (error) {
            setStatus(error.message, true);
        }
    }

    async function save(event) {
        event.preventDefault();
        setStatus("Saving BIRD settings...", false);
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/global-settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(readForm()),
            });
            render(data);
            setStatus("Saved.", false);
        } catch (error) {
            setStatus(error.message, true);
        }
    }

    async function runServiceAction(action) {
        const resolvedAction = action === "start-restart" && currentServiceState === "RUNNING" ? "restart" : action === "start-restart" ? "start" : action;
        setStatus("Queueing BIRD service action...", false);
        await HF.fetchJson("/api/services/status/bird/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({action: resolvedAction}),
        });
        setStatus("Service action queued.", false);
        await loadWorkRequests();
        await load();
    }

    function renderWorkRequests(data) {
        const requests = data.requests || [];
        if (workRequestsCount) {
            workRequestsCount.textContent = `requests=${requests.length}`;
        }
        if (!workRequestsBody) {
            return;
        }
        if (!requests.length) {
            workRequestsBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no BIRD work requests</span></div></td>
                </tr>
            `;
            return;
        }
        workRequestsBody.innerHTML = requests.map((request) => {
            const failed = request.status === "failed";
            const status = failed ? "down" : request.status === "success" ? "up" : "disabled";
            return `
                <tr>
                    <td>${HF.escapeHtml(request.id)}</td>
                    <td><span class="status ${status}">${HF.escapeHtml(request.status)}</span></td>
                    <td>${HF.escapeHtml(request.action_name || "-")}</td>
                    <td>${HF.escapeHtml(request.updated_at || "-")}</td>
                    <td>${HF.escapeHtml(request.error_message || "")}</td>
                </tr>
            `;
        }).join("");
    }

    async function loadWorkRequests() {
        if (workRequestsLoading || !workRequestsPanel || workRequestsPanel.hidden) {
            return;
        }
        workRequestsLoading = true;
        try {
            const data = await HF.fetchJson("/api/work-requests?category=SERVICE_MANAGEMENT.SERVICE_CONTROL&service_name=bird&include_payload=true");
            renderWorkRequests(data);
        } catch (error) {
            if (workRequestsBody) {
                workRequestsBody.innerHTML = `
                    <tr>
                        <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
        } finally {
            workRequestsLoading = false;
        }
    }

    async function runPendingAction() {
        if (!pendingAction || !pendingAction.run) {
            closeActionModal();
            return;
        }
        if (actionConfirm) {
            actionConfirm.disabled = true;
        }
        try {
            await pendingAction.run();
            closeActionModal();
        } catch (error) {
            if (actionMessage) {
                actionMessage.textContent = error.message;
            }
            if (actionConfirm) {
                actionConfirm.disabled = false;
            }
        }
    }

    viewButtons.forEach((button) => {
        button.addEventListener("click", () => setActiveView(button.dataset.routingView || "global-config"));
    });
    if (form) {
        form.addEventListener("submit", save);
    }
    document.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-bird-service-action]");
        if (actionButton) {
            const action = actionButton.dataset.birdServiceAction;
            const label = action === "start-restart" ? "START / RESTART BIRD service" : `${HF.text(action).toUpperCase()} BIRD service`;
            openActionModal(action, label, () => runServiceAction(action));
            return;
        }
        if (event.target.closest("[data-bird-modal-cancel]") || event.target === actionModal) {
            closeActionModal();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeActionModal();
        }
    });
    if (actionConfirm) {
        actionConfirm.addEventListener("click", runPendingAction);
    }

    setActiveView("global-config");
    load();
})();
