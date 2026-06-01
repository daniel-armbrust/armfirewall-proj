(function () {
    const birdState = document.querySelector("#routing-bird-state");
    const birdVersion = document.querySelector("#routing-bird-version");
    const birdPid = document.querySelector("#routing-bird-pid");
    const birdUptime = document.querySelector("#routing-bird-uptime");
    const form = document.querySelector("#bird-global-settings-form");
    const status = document.querySelector("#bird-global-settings-status");
    const ripForm = document.querySelector("#bird-rip-settings-form");
    const ripStatus = document.querySelector("#bird-rip-settings-status");
    const actionModal = document.querySelector("#bird-action-modal");
    const actionTitle = document.querySelector("#bird-action-title");
    const actionMessage = document.querySelector("#bird-action-message");
    const actionConfirm = document.querySelector("[data-bird-modal-confirm]");
    const logsPanel = document.querySelector("#bird-logs-panel");
    const logsOutput = document.querySelector("#bird-logs-output");
    const logsCount = document.querySelector("#bird-logs-count");
    const workRequestsPanel = document.querySelector("#bird-work-requests-panel");
    const workRequestsBody = document.querySelector("#bird-work-requests-body");
    const workRequestsCount = document.querySelector("#bird-work-requests-count");
    const viewButtons = Array.from(document.querySelectorAll("[data-routing-view]"));
    const panels = {
        "global-config": document.querySelector("#routing-global-config-panel"),
        rip: document.querySelector("#routing-rip-panel"),
        ospf: document.querySelector("#routing-ospf-panel"),
        bgp: document.querySelector("#routing-bgp-panel"),
        logs: logsPanel,
        "work-requests": workRequestsPanel,
    };

    const fields = {
        router_id: document.querySelector("#bird-router-id"),
        hostname: document.querySelector("#bird-hostname"),
        kernel: {
            enabled: document.querySelector("#bird-kernel-enabled"),
            route_table: document.querySelector("#bird-kernel-route-table"),
            learn: document.querySelector("#bird-kernel-learn"),
            channel_family: document.querySelector("#bird-kernel-channel-family"),
            channel_table_name: document.querySelector("#bird-kernel-channel-table-name"),
            import_policy: document.querySelector("#bird-kernel-import-policy"),
            export_policy: document.querySelector("#bird-kernel-export-policy"),
            metric: document.querySelector("#bird-kernel-metric"),
            scan_time_secs: document.querySelector("#bird-kernel-scan-time-secs"),
            persist: document.querySelector("#bird-kernel-persist"),
        },
        device: {
            enabled: document.querySelector("#bird-device-enabled"),
            iface_name: document.querySelector("#bird-device-iface-name"),
            scan_time_secs: document.querySelector("#bird-device-scan-time-secs"),
        },
        direct: {
            enabled: document.querySelector("#bird-direct-enabled"),
            iface_name: document.querySelector("#bird-direct-iface-name"),
        },
        rip: {
            enabled: document.querySelector("#bird-rip-enabled"),
            version: document.querySelector("#bird-rip-version"),
            mode: document.querySelector("#bird-rip-mode"),
            multicast_addr: document.querySelector("#bird-rip-multicast-addr"),
            passive: document.querySelector("#bird-rip-passive"),
            port: document.querySelector("#bird-rip-port"),
            update_time_secs: document.querySelector("#bird-rip-update-time-secs"),
            timeout_time_secs: document.querySelector("#bird-rip-timeout-time-secs"),
            garbage_time_secs: document.querySelector("#bird-rip-garbage-time-secs"),
            authentication: document.querySelector("#bird-rip-authentication"),
            password: document.querySelector("#bird-rip-password"),
        },
    };
    let currentServiceState = "";
    let pendingAction = null;
    let logsLoading = false;
    let ripLoading = false;
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

    function setRipStatus(message, isError) {
        if (!ripStatus) {
            return;
        }
        ripStatus.textContent = message;
        ripStatus.hidden = !message;
        ripStatus.classList.toggle("error", Boolean(isError));
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
        if (selectedView === "logs") {
            loadLogs();
        }
        if (selectedView === "rip") {
            loadRip();
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

    function setFieldValue(element, value) {
        if (!element) {
            return;
        }
        if (element.type === "checkbox") {
            element.checked = Boolean(value);
            return;
        }
        element.value = value === undefined || value === null ? "" : String(value);
    }

    function readFieldValue(element) {
        if (!element) {
            return "";
        }
        return element.type === "checkbox" ? element.checked : element.value;
    }

    function option(label, value) {
        const item = document.createElement("option");
        item.value = value === undefined || value === null ? "" : String(value);
        item.textContent = label;
        return item;
    }

    function renderRoutingTableOptions(tables, selectedRouteTable, selectedTableName) {
        const routeTableSelect = fields.kernel.route_table;
        const channelTableSelect = fields.kernel.channel_table_name;
        if (routeTableSelect) {
            routeTableSelect.innerHTML = "";
            (tables || []).forEach((table) => {
                const label = `${HF.text(table.table_id)} : ${HF.text(table.table_name)}`;
                routeTableSelect.appendChild(option(label, table.table_id));
            });
            setFieldValue(routeTableSelect, selectedRouteTable);
        }
        if (channelTableSelect) {
            channelTableSelect.innerHTML = "";
            channelTableSelect.appendChild(option("-", ""));
            (tables || []).forEach((table) => {
                channelTableSelect.appendChild(option(table.table_name, table.table_name));
            });
            setFieldValue(channelTableSelect, selectedTableName || "main");
        }
    }

    function renderInterfaceOptions(interfaces, deviceIface, directIface) {
        [fields.device.iface_name, fields.direct.iface_name].forEach((select) => {
            if (!select) {
                return;
            }
            select.innerHTML = "";
            select.appendChild(option("-", ""));
            select.appendChild(option("any - all interfaces", "*"));
            (interfaces || []).forEach((iface) => {
                const description = HF.text(iface.description || "-");
                const label = `${HF.text(iface.name)} - ${description}`;
                select.appendChild(option(label, iface.name));
            });
        });
        setFieldValue(fields.device.iface_name, deviceIface || "");
        setFieldValue(fields.direct.iface_name, directIface || "");
    }

    function populateForm(settings, data) {
        const kernel = settings.kernel || {};
        const device = settings.device || {};
        const direct = settings.direct || {};
        renderRoutingTableOptions(data.routing_tables || [], kernel.route_table, kernel.channel_table_name);
        renderInterfaceOptions(data.interfaces || [], device.iface_name, direct.iface_name);
        setFieldValue(fields.router_id, settings.router_id);
        setFieldValue(fields.hostname, settings.hostname);
        Object.entries(fields.kernel).forEach(([name, element]) => setFieldValue(element, kernel[name]));
        Object.entries(fields.device).forEach(([name, element]) => setFieldValue(element, device[name]));
        Object.entries(fields.direct).forEach(([name, element]) => setFieldValue(element, direct[name]));
    }

    function readForm() {
        return {
            router_id: readFieldValue(fields.router_id),
            hostname: readFieldValue(fields.hostname),
            kernel: {
                enabled: readFieldValue(fields.kernel.enabled),
                route_table: readFieldValue(fields.kernel.route_table),
                learn: readFieldValue(fields.kernel.learn),
                channel_family: readFieldValue(fields.kernel.channel_family),
                channel_table_name: readFieldValue(fields.kernel.channel_table_name),
                import_policy: readFieldValue(fields.kernel.import_policy),
                export_policy: readFieldValue(fields.kernel.export_policy),
                metric: readFieldValue(fields.kernel.metric),
                scan_time_secs: readFieldValue(fields.kernel.scan_time_secs),
                persist: readFieldValue(fields.kernel.persist),
            },
            device: {
                enabled: readFieldValue(fields.device.enabled),
                iface_name: readFieldValue(fields.device.iface_name),
                scan_time_secs: readFieldValue(fields.device.scan_time_secs),
            },
            direct: {
                enabled: readFieldValue(fields.direct.enabled),
                iface_name: readFieldValue(fields.direct.iface_name),
            },
        };
    }

    function applyRipVersionDefaults() {
        const version = readFieldValue(fields.rip.version);
        if (version === "ng") {
            setFieldValue(fields.rip.mode, "multicast");
            setFieldValue(fields.rip.multicast_addr, "ff02::9");
            setFieldValue(fields.rip.port, "521");
            if (fields.rip.mode) {
                fields.rip.mode.disabled = true;
            }
            return;
        }
        if (fields.rip.mode) {
            fields.rip.mode.disabled = false;
        }
        if (!readFieldValue(fields.rip.multicast_addr) || readFieldValue(fields.rip.multicast_addr) === "ff02::9") {
            setFieldValue(fields.rip.multicast_addr, "224.0.0.9");
        }
        if (!readFieldValue(fields.rip.port) || readFieldValue(fields.rip.port) === "521") {
            setFieldValue(fields.rip.port, "520");
        }
    }

    function populateRipForm(settings) {
        Object.entries(fields.rip).forEach(([name, element]) => setFieldValue(element, settings[name]));
        applyRipVersionDefaults();
    }

    function readRipForm() {
        return {
            enabled: readFieldValue(fields.rip.enabled),
            version: readFieldValue(fields.rip.version),
            mode: readFieldValue(fields.rip.mode),
            multicast_addr: readFieldValue(fields.rip.multicast_addr),
            passive: readFieldValue(fields.rip.passive),
            port: readFieldValue(fields.rip.port),
            update_time_secs: readFieldValue(fields.rip.update_time_secs),
            timeout_time_secs: readFieldValue(fields.rip.timeout_time_secs),
            garbage_time_secs: readFieldValue(fields.rip.garbage_time_secs),
            authentication: readFieldValue(fields.rip.authentication),
            password: readFieldValue(fields.rip.password),
        };
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
        populateForm(settings, data);
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

    async function loadRip() {
        if (ripLoading) {
            return;
        }
        ripLoading = true;
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/rip-settings");
            populateRipForm(data.settings || {});
        } catch (error) {
            setRipStatus(error.message, true);
        } finally {
            ripLoading = false;
        }
    }

    async function saveRip(event) {
        event.preventDefault();
        applyRipVersionDefaults();
        setRipStatus("Saving RIP settings...", false);
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/rip-settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(readRipForm()),
            });
            populateRipForm(data.settings || {});
            setRipStatus("Saved.", false);
        } catch (error) {
            setRipStatus(error.message, true);
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

    function renderLogs(data) {
        const lines = data.lines || [];
        if (logsCount) {
            logsCount.textContent = `lines=${lines.length}`;
        }
        if (logsOutput) {
            logsOutput.textContent = lines.length ? lines.join("\n") : "bird.out.log is empty.";
        }
    }

    async function loadLogs() {
        if (logsLoading || !logsPanel || logsPanel.hidden) {
            return;
        }
        logsLoading = true;
        try {
            renderLogs(await HF.fetchJson("/api/network/routing-protocols/bird/logs"));
        } catch (error) {
            if (logsOutput) {
                logsOutput.textContent = error.message;
            }
            if (logsCount) {
                logsCount.textContent = "lines=0";
            }
        } finally {
            logsLoading = false;
        }
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
    if (ripForm) {
        ripForm.addEventListener("submit", saveRip);
    }
    if (fields.rip.version) {
        fields.rip.version.addEventListener("change", applyRipVersionDefaults);
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
