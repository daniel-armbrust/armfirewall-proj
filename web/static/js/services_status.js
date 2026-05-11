(function () {
    const stateLabel = document.querySelector("#services-status-state");
    const servicesBody = document.querySelector("#armfirewall-services-body");
    const servicesCount = document.querySelector("#armfirewall-services-count");
    const optionalBody = document.querySelector("#optional-services-body");
    const optionalCount = document.querySelector("#optional-services-count");
    const actionModal = document.querySelector("#service-action-modal");
    const actionMessage = document.querySelector("#service-action-message");
    const actionConfirm = document.querySelector("[data-service-action-confirm]");
    const optionalServiceModal = document.querySelector("#optional-service-modal");
    const optionalServiceTitle = document.querySelector("#optional-service-title");
    const optionalServiceMessage = document.querySelector("#optional-service-message");
    const optionalServiceConfirm = document.querySelector("[data-optional-service-confirm]");
    let pendingAction = null;
    let pendingOptionalAction = null;
    let loading = false;
    const POLL_MS = 5000;

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

    function setMetric(id, value) {
        const element = document.querySelector(id);
        if (element) {
            element.textContent = HF.text(value);
        }
    }

    function statusClass(value) {
        const text = String(value || "").toLowerCase();
        if (["active", "enabled", "running"].includes(text)) {
            return "up";
        }
        if (["failed", "fatal", "exited", "stopped"].includes(text)) {
            return "down";
        }
        return "disabled";
    }

    function renderArmFirewallServices(services) {
        if (!servicesBody) {
            return;
        }
        if (!services.length) {
            servicesBody.innerHTML = `
                <tr>
                    <td colspan="7"><div class="terminal-empty"><span class="prompt">$</span><span>no ArmFirewall services</span></div></td>
                </tr>
            `;
            return;
        }
        servicesBody.innerHTML = services.map((service) => {
            const protectedService = Boolean(service.protected);
            const running = String(service.state || "").toUpperCase() === "RUNNING";
            const installed = Boolean(service.installed);
            const protectedBadge = protectedService ? '<span class="status protected">PROTECTED</span>' : "";
            const startDisabled = protectedService || !installed || running ? "disabled" : "";
            const stopDisabled = protectedService || !installed || !running ? "disabled" : "";
            const restartDisabled = protectedService || !installed ? "disabled" : "";
            return `
                <tr>
                    <td><strong>${HF.escapeHtml(service.name)}</strong> ${protectedBadge}</td>
                    <td>${HF.escapeHtml(service.kind)}</td>
                    <td><span class="status ${statusClass(service.state)}">${HF.escapeHtml(service.state)}</span></td>
                    <td>${HF.escapeHtml(service.pid)}</td>
                    <td>${HF.escapeHtml(service.uptime)}</td>
                    <td>${HF.escapeHtml(service.description)}</td>
                    <td>
                        <button class="text-button compact" type="button" data-service-action="start" data-service-name="${HF.escapeHtml(service.name)}" ${startDisabled}>Start</button>
                        <button class="text-button compact" type="button" data-service-action="restart" data-service-name="${HF.escapeHtml(service.name)}" ${restartDisabled}>Restart</button>
                        <button class="text-button compact danger" type="button" data-service-action="stop" data-service-name="${HF.escapeHtml(service.name)}" ${stopDisabled}>Stop</button>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function renderOptionalServices(services) {
        if (!optionalBody) {
            return;
        }
        if (!services.length) {
            optionalBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no optional services</span></div></td>
                </tr>
            `;
            return;
        }
        optionalBody.innerHTML = services.map((service) => {
            const installed = Boolean(service.installed);
            const installDisabled = service.can_install ? "" : "disabled";
            const startDisabled = installed && String(service.state || "").toUpperCase() !== "RUNNING" ? "" : "disabled";
            const restartDisabled = installed ? "" : "disabled";
            const stopDisabled = installed && String(service.state || "").toUpperCase() === "RUNNING" ? "" : "disabled";
            const uninstallDisabled = installed ? "" : "disabled";
            return `
                <tr>
                    <td><strong>${HF.escapeHtml(service.display_name)}</strong><br><span class="muted">${HF.escapeHtml(service.name)}</span></td>
                    <td>${HF.escapeHtml(service.package)}</td>
                    <td><span class="status ${statusClass(service.state)}">${HF.escapeHtml(service.state)}</span></td>
                    <td>${HF.escapeHtml(service.description)}</td>
                    <td>
                        <button class="text-button compact primary" type="button" data-optional-service-action="install" data-optional-service-name="${HF.escapeHtml(service.name)}" ${installDisabled}>Install</button>
                        <button class="text-button compact" type="button" data-service-action="start" data-service-name="${HF.escapeHtml(service.name)}" ${startDisabled}>Start</button>
                        <button class="text-button compact" type="button" data-service-action="restart" data-service-name="${HF.escapeHtml(service.name)}" ${restartDisabled}>Restart</button>
                        <button class="text-button compact danger" type="button" data-service-action="stop" data-service-name="${HF.escapeHtml(service.name)}" ${stopDisabled}>Stop</button>
                        <button class="text-button compact danger" type="button" data-optional-service-action="uninstall" data-optional-service-name="${HF.escapeHtml(service.name)}" ${uninstallDisabled}>Uninstall</button>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function openActionModal(serviceName, action) {
        pendingAction = {serviceName, action};
        if (actionMessage) {
            actionMessage.textContent = `${action.toUpperCase()} ${serviceName}?`;
        }
        if (actionModal) {
            actionModal.hidden = false;
        }
    }

    function closeActionModal() {
        pendingAction = null;
        if (actionModal) {
            actionModal.hidden = true;
        }
    }

    function openOptionalServiceModal(serviceName, action) {
        pendingOptionalAction = {serviceName, action};
        if (optionalServiceTitle) {
            optionalServiceTitle.textContent = action === "uninstall" ? "Uninstall optional service" : "Install optional service";
        }
        if (optionalServiceMessage) {
            optionalServiceMessage.textContent = `${action.toUpperCase()} ${serviceName}? This will create a work request.`;
        }
        if (optionalServiceConfirm) {
            optionalServiceConfirm.textContent = action === "uninstall" ? "Uninstall" : "Install";
            optionalServiceConfirm.classList.toggle("danger", action === "uninstall");
        }
        if (optionalServiceModal) {
            optionalServiceModal.hidden = false;
        }
    }

    function closeOptionalServiceModal() {
        pendingOptionalAction = null;
        if (optionalServiceModal) {
            optionalServiceModal.hidden = true;
        }
    }

    async function pollServices() {
        if (loading) {
            return;
        }
        loading = true;
        try {
            setState("Polling");
            const data = await HF.fetchJson("/api/services/status");
            const summary = data.summary || {};
            const services = data.services || [];
            const optionalServices = data.optional_services || [];
            setMetric("#services-summary-total", summary.services);
            setMetric("#services-summary-active", summary.installed);
            setMetric("#services-summary-inactive", summary.running);
            setMetric("#services-summary-supervisor", summary.inactive);
            if (servicesCount) {
                servicesCount.textContent = `services=${HF.number(summary.services).toLocaleString()}`;
            }
            if (optionalCount) {
                optionalCount.textContent = `services=${HF.number(optionalServices.length).toLocaleString()}`;
            }
            renderArmFirewallServices(services);
            renderOptionalServices(optionalServices);
            setState("Live", summary.updated_at || "-");
        } catch (error) {
            setState("Offline");
            if (servicesBody) {
                servicesBody.innerHTML = `
                    <tr>
                        <td colspan="7"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
        } finally {
            loading = false;
        }
    }

    async function runPendingAction() {
        if (!pendingAction || !actionConfirm) {
            return;
        }
        const {serviceName, action} = pendingAction;
        actionConfirm.disabled = true;
        try {
            setState(action);
            await HF.fetchJson(`/api/services/status/${encodeURIComponent(serviceName)}/action`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({action}),
            });
            closeActionModal();
            await pollServices();
        } catch (error) {
            if (actionMessage) {
                actionMessage.textContent = error.message;
            }
        } finally {
            actionConfirm.disabled = false;
        }
    }

    async function runPendingOptionalServiceAction() {
        if (!pendingOptionalAction || !optionalServiceConfirm) {
            return;
        }
        const {serviceName, action} = pendingOptionalAction;
        optionalServiceConfirm.disabled = true;
        try {
            setState(action === "uninstall" ? "Uninstalling" : "Installing");
            await HF.fetchJson(`/api/services/status/${encodeURIComponent(serviceName)}/${encodeURIComponent(action)}`, {
                method: "POST",
            });
            closeOptionalServiceModal();
            await pollServices();
        } catch (error) {
            if (optionalServiceMessage) {
                optionalServiceMessage.textContent = error.message;
            }
        } finally {
            optionalServiceConfirm.disabled = false;
        }
    }

    document.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-service-action]");
        if (actionButton) {
            openActionModal(actionButton.dataset.serviceName, actionButton.dataset.serviceAction);
            return;
        }
        const optionalButton = event.target.closest("[data-optional-service-action]");
        if (optionalButton) {
            openOptionalServiceModal(optionalButton.dataset.optionalServiceName, optionalButton.dataset.optionalServiceAction);
            return;
        }
        if (event.target.closest("[data-service-action-cancel]")) {
            closeActionModal();
        }
        if (event.target.closest("[data-optional-service-cancel]")) {
            closeOptionalServiceModal();
        }
    });

    if (actionConfirm) {
        actionConfirm.addEventListener("click", runPendingAction);
    }
    if (optionalServiceConfirm) {
        optionalServiceConfirm.addEventListener("click", runPendingOptionalServiceAction);
    }

    pollServices();
    setInterval(pollServices, POLL_MS);
}());
