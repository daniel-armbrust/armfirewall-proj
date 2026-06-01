(function () {
    const birdState = document.querySelector("#routing-bird-state");
    const birdVersion = document.querySelector("#routing-bird-version");
    const birdPid = document.querySelector("#routing-bird-pid");
    const birdUptime = document.querySelector("#routing-bird-uptime");
    const form = document.querySelector("#bird-global-settings-form");
    const status = document.querySelector("#bird-global-settings-status");
    const ripForm = document.querySelector("#bird-rip-settings-form");
    const ripStatus = document.querySelector("#bird-rip-settings-status");
    const ripPasswordToggle = document.querySelector("#bird-rip-password-toggle");
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
    const routingServiceActions = document.querySelector(".routing-service-actions");
    const serviceActionTabs = document.querySelector(".service-action-tabs");
    const contextButtons = Array.from(document.querySelectorAll("[data-routing-context-button]"));
    const diagnosticsPanel = document.querySelector("#bird-diagnostics-panel");
    const diagnosticsSummary = document.querySelector("#bird-diagnostics-summary");
    const diagnosticsMeta = document.querySelector("#bird-diagnostics-meta");
    const diagnosticsBody = document.querySelector("#bird-diagnostics-protocols-body");
    const diagnosticsOutput = document.querySelector("#bird-diagnostics-output");
    const viewButtons = Array.from(document.querySelectorAll("[data-routing-view]"));
    const WORK_REQUEST_REFRESH_MS = 3000;
    const DIAGNOSTICS_REFRESH_MS = 5000;
    const panels = {
        "global-config": document.querySelector("#routing-global-config-panel"),
        rip: document.querySelector("#routing-rip-panel"),
        ospf: document.querySelector("#routing-ospf-panel"),
        bgp: document.querySelector("#routing-bgp-panel"),
        logs: logsPanel,
        diagnostics: diagnosticsPanel,
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
            iface_names: document.querySelector("#bird-rip-iface-names"),
            address_label: document.querySelector("#bird-rip-address-label"),
            multicast_addr: document.querySelector("#bird-rip-multicast-addr"),
            import_policy: document.querySelector("#bird-rip-import-policy"),
            export_policy: document.querySelector("#bird-rip-export-policy"),
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
    let routingSettingsContext = "global-config";
    let pendingAction = null;
    let logsLoading = false;
    let ripLoading = false;
    let ripSelectedInterfaceValues = ["*"];
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

    function scrollToTop() {
        document.querySelector("#main-content")?.scrollTo({top: 0, behavior: "smooth"});
        document.documentElement.scrollTo({top: 0, behavior: "smooth"});
        document.body.scrollTo({top: 0, behavior: "smooth"});
        window.scrollTo({top: 0, behavior: "smooth"});
    }

    function setRipPasswordVisible(visible) {
        if (!fields.rip.password || !ripPasswordToggle) {
            return;
        }
        fields.rip.password.type = visible ? "text" : "password";
        ripPasswordToggle.setAttribute("aria-pressed", visible ? "true" : "false");
        ripPasswordToggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
        ripPasswordToggle.setAttribute("title", visible ? "Hide password" : "Show password");
        ripPasswordToggle.textContent = visible ? "◌" : "◉";
    }

    function syncRipAuthenticationPassword(source) {
        const auth = fields.rip.authentication;
        const password = fields.rip.password;
        if (!auth || !password) {
            return;
        }
        const noneOption = Array.from(auth.options).find((option) => option.value === "none");
        if (source === "authentication" && auth.value === "none") {
            password.value = "";
            if (noneOption) {
                noneOption.disabled = false;
            }
            return;
        }

        const hasPassword = password.value.trim() !== "";
        if (noneOption) {
            noneOption.disabled = hasPassword;
        }
        if (hasPassword && auth.value === "none") {
            auth.value = "cryptographic";
        }
    }

    function handleRipAuthenticationChange() {
        syncRipAuthenticationPassword("authentication");
    }

    function handleRipPasswordInput() {
        syncRipAuthenticationPassword("password");
    }

    function workRequestsVisible() {
        return Boolean(workRequestsPanel && !workRequestsPanel.hidden);
    }

    function diagnosticsVisible() {
        return Boolean(diagnosticsPanel && !diagnosticsPanel.hidden);
    }

    function setRoutingNavigationContext(selectedView) {
        const unimplementedProtocol = selectedView === "ospf" || selectedView === "bgp";
        if (selectedView === "rip") {
            routingSettingsContext = "rip";
        } else if (selectedView !== "diagnostics") {
            routingSettingsContext = "global-config";
        }

        if (routingServiceActions) {
            routingServiceActions.hidden = unimplementedProtocol;
        }
        if (serviceActionTabs) {
            serviceActionTabs.hidden = routingSettingsContext === "rip";
        }
        contextButtons.forEach((button) => {
            button.hidden = button.dataset.routingContextButton !== routingSettingsContext;
        });
    }

    function isRoutingButtonActive(button, selectedView) {
        if (button.dataset.routingView === selectedView) {
            return true;
        }
        return selectedView === "diagnostics" && button.dataset.routingView === "diagnostics";
    }

    function setActiveView(viewName) {
        const selectedView = panels[viewName] ? viewName : "global-config";
        setRoutingNavigationContext(selectedView);
        Object.entries(panels).forEach(([name, panel]) => {
            if (panel) {
                panel.hidden = name !== selectedView;
            }
        });
        viewButtons.forEach((button) => {
            button.classList.toggle("active", isRoutingButtonActive(button, selectedView));
        });
        if (selectedView === "work-requests") {
            workRequestsLoading = false;
            loadWorkRequests({force: true});
        }
        if (selectedView === "logs") {
            loadLogs();
        }
        if (selectedView === "diagnostics") {
            loadDiagnostics({force: true});
        }
        if (selectedView === "rip") {
            loadRip();
        }
    }

    async function showWorkRequests() {
        setActiveView("work-requests");
        workRequestsLoading = false;
        await loadWorkRequests({force: true});
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

    function openActionModal(action, label, run, title = "Confirm action") {
        pendingAction = {action, run};
        if (actionTitle) {
            actionTitle.textContent = title;
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
                const label = `${HF.text(table.table_name)} (${HF.text(table.table_id)})`;
                routeTableSelect.appendChild(option(label, table.table_id));
            });
            setFieldValue(routeTableSelect, selectedRouteTable);
        }
        if (channelTableSelect) {
            channelTableSelect.innerHTML = "";
            channelTableSelect.appendChild(option("-", ""));
            setFieldValue(channelTableSelect, "");
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
        renderRipInterfaceOptions(interfaces || []);
    }

    function selectedRipInterfaces() {
        const select = fields.rip.iface_names;
        if (!select) {
            return ["*"];
        }
        const selected = Array.from(select.selectedOptions).map((option) => option.value).filter(Boolean);
        return selected.length ? selected : ["*"];
    }

    function setSelectedRipInterfaces(values) {
        const select = fields.rip.iface_names;
        ripSelectedInterfaceValues = (Array.isArray(values) && values.length ? values : ["*"]).map(String);
        if (!select) {
            return;
        }
        const selected = new Set(ripSelectedInterfaceValues);
        Array.from(select.options).forEach((option) => {
            option.selected = selected.has(option.value);
        });
    }

    function normalizeRipInterfaceSelection() {
        const select = fields.rip.iface_names;
        if (!select) {
            return;
        }
        const selected = selectedRipInterfaces();
        if (selected.includes("*") && selected.length > 1) {
            setSelectedRipInterfaces(["*"]);
            return;
        }
        ripSelectedInterfaceValues = selected;
    }

    function renderRipInterfaceOptions(interfaces) {
        const select = fields.rip.iface_names;
        if (!select) {
            return;
        }
        const selected = ripSelectedInterfaceValues.length ? ripSelectedInterfaceValues : selectedRipInterfaces();
        select.innerHTML = "";
        select.appendChild(option("all - all interfaces", "*"));
        interfaces.forEach((iface) => {
            const description = HF.text(iface.description || "-");
            const label = `${HF.text(iface.name)} - ${description}`;
            select.appendChild(option(label, iface.name));
        });
        setSelectedRipInterfaces(selected);
        normalizeRipInterfaceSelection();
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
            setText(fields.rip.address_label, "Multicast Address");
            setFieldValue(fields.rip.mode, "multicast");
            setFieldValue(fields.rip.multicast_addr, "ff02::9");
            setFieldValue(fields.rip.port, "521");
            if (fields.rip.mode) {
                fields.rip.mode.disabled = true;
            }
            return;
        }
        if (version === "1") {
            setText(fields.rip.address_label, "Broadcast Address");
            setFieldValue(fields.rip.mode, "broadcast");
            setFieldValue(fields.rip.multicast_addr, "255.255.255.255");
            setFieldValue(fields.rip.port, "520");
            if (fields.rip.mode) {
                fields.rip.mode.disabled = true;
            }
            return;
        }
        if (fields.rip.mode) {
            fields.rip.mode.disabled = false;
        }
        const mode = readFieldValue(fields.rip.mode);
        setText(fields.rip.address_label, mode === "broadcast" ? "Broadcast Address" : "Multicast Address");
        if (mode === "broadcast") {
            setFieldValue(fields.rip.multicast_addr, "255.255.255.255");
        } else if (!readFieldValue(fields.rip.multicast_addr) || ["ff02::9", "255.255.255.255"].includes(readFieldValue(fields.rip.multicast_addr))) {
            setFieldValue(fields.rip.multicast_addr, "224.0.0.9");
        }
        if (!readFieldValue(fields.rip.port) || readFieldValue(fields.rip.port) === "521") {
            setFieldValue(fields.rip.port, "520");
        }
    }

    function populateRipForm(settings) {
        Object.entries(fields.rip).forEach(([name, element]) => {
            if (name !== "address_label" && name !== "iface_names") {
                setFieldValue(element, settings[name]);
            }
        });
        setSelectedRipInterfaces(settings.iface_names);
        applyRipVersionDefaults();
        syncRipAuthenticationPassword();
    }

    function readRipForm() {
        return {
            enabled: readFieldValue(fields.rip.enabled),
            version: readFieldValue(fields.rip.version),
            mode: readFieldValue(fields.rip.mode),
            iface_names: selectedRipInterfaces(),
            multicast_addr: readFieldValue(fields.rip.multicast_addr),
            import_policy: readFieldValue(fields.rip.import_policy),
            export_policy: readFieldValue(fields.rip.export_policy),
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

    function confirmSave(event) {
        event.preventDefault();
        openActionModal(
            "save-global-config",
            "Save this BIRD configuration?",
            saveGlobalSettings,
            "Save configuration",
        );
    }

    async function saveGlobalSettings() {
        setStatus("Saving BIRD settings...", false);
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/global-settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(readForm()),
            });
            render(data);
            setStatus("", false);
            await showWorkRequests();
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

    function confirmSaveRip(event) {
        event.preventDefault();
        openActionModal(
            "save-rip-config",
            "Save this RIP configuration?",
            saveRipSettings,
            "Save configuration",
        );
    }

    async function saveRipSettings() {
        applyRipVersionDefaults();
        setRipStatus("Saving RIP settings...", false);
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/rip-settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(readRipForm()),
            });
            populateRipForm(data.settings || {});
            setRipStatus("", false);
            await showWorkRequests();
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
        await showWorkRequests();
    }

    function renderLogs(data) {
        const lines = data.lines || [];
        if (logsCount) {
            logsCount.textContent = `lines=${lines.length}`;
        }
        if (logsOutput) {
            logsOutput.textContent = lines.length ? lines.join("\n") : "bird stdout/stderr logs are empty.";
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

    function diagnosticStateClass(state) {
        const normalized = String(state || "").toLowerCase();
        if (normalized === "up") {
            return "up";
        }
        if (normalized === "down" || normalized === "start" || normalized === "stop") {
            return "down";
        }
        return "disabled";
    }

    function renderDiagnostics(data) {
        const run = data.last_run;
        const protocols = data.protocols || [];
        const collectedAt = run?.collected_at ? String(run.collected_at).split(" ").pop() : "-";
        if (diagnosticsSummary) {
            diagnosticsSummary.textContent = run
                ? `UPDATED ${HF.text(collectedAt)} | ${HF.text(run.duration_ms ?? "-")}ms`
                : "NO SNAPSHOT";
        }
        if (diagnosticsMeta) {
            diagnosticsMeta.textContent = "";
        }
        if (diagnosticsBody) {
            if (!protocols.length) {
                diagnosticsBody.innerHTML = `
                    <tr>
                        <td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>no protocol rows collected</span></div></td>
                    </tr>
                `;
            } else {
                diagnosticsBody.innerHTML = protocols.map((protocol) => `
                    <tr>
                        <td>${HF.escapeHtml(protocol.name || "-")}</td>
                        <td>${HF.escapeHtml(protocol.proto || "-")}</td>
                        <td>${HF.escapeHtml(protocol.table_name || "-")}</td>
                        <td><span class="status ${diagnosticStateClass(protocol.state)}">${HF.escapeHtml(protocol.state || "-")}</span></td>
                        <td>${HF.escapeHtml(protocol.since || "-")}</td>
                        <td>${HF.escapeHtml(protocol.info || "")}</td>
                    </tr>
                `).join("");
            }
        }
        if (diagnosticsOutput) {
            const output = data.raw_output || data.error_output || "No raw output collected.";
            diagnosticsOutput.textContent = output.trim() || "No raw output collected.";
        }
    }

    let diagnosticsLoading = false;
    async function loadDiagnostics(options = {}) {
        if (!diagnosticsPanel || diagnosticsPanel.hidden) {
            return;
        }
        if (diagnosticsLoading && !options.force) {
            return;
        }
        diagnosticsLoading = true;
        try {
            renderDiagnostics(await HF.fetchJson("/api/network/routing-protocols/bird/diagnostics"));
        } catch (error) {
            if (diagnosticsMeta) {
                diagnosticsMeta.textContent = error.message;
            }
            if (diagnosticsBody) {
                diagnosticsBody.innerHTML = `
                    <tr>
                        <td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
            if (diagnosticsOutput) {
                diagnosticsOutput.textContent = error.message;
            }
        } finally {
            diagnosticsLoading = false;
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

    async function loadWorkRequests(options = {}) {
        if (!workRequestsPanel || workRequestsPanel.hidden) {
            return;
        }
        if (workRequestsLoading && !options.force) {
            return;
        }
        if (workRequestsLoading) {
            return;
        }
        workRequestsLoading = true;
        try {
            const data = await HF.fetchJson("/api/work-requests?category=SERVICE_MANAGEMENT.BIRD_CONFIG&category=SERVICE_MANAGEMENT.SERVICE_CONTROL&service_name=bird&include_payload=true");
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
        form.addEventListener("submit", confirmSave);
    }
    if (ripForm) {
        ripForm.addEventListener("submit", confirmSaveRip);
    }
    if (fields.rip.version) {
        fields.rip.version.addEventListener("change", applyRipVersionDefaults);
    }
    if (fields.rip.mode) {
        fields.rip.mode.addEventListener("change", applyRipVersionDefaults);
    }
    if (fields.rip.iface_names) {
        fields.rip.iface_names.addEventListener("change", normalizeRipInterfaceSelection);
    }
    if (fields.rip.authentication) {
        fields.rip.authentication.addEventListener("change", handleRipAuthenticationChange);
    }
    if (fields.rip.password) {
        fields.rip.password.addEventListener("input", handleRipPasswordInput);
    }
    if (ripPasswordToggle) {
        ripPasswordToggle.addEventListener("click", () => {
            setRipPasswordVisible(fields.rip.password?.type === "password");
        });
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
    window.setInterval(() => {
        if (workRequestsVisible()) {
            loadWorkRequests();
        }
    }, WORK_REQUEST_REFRESH_MS);
    window.setInterval(() => {
        if (diagnosticsVisible()) {
            loadDiagnostics();
        }
    }, DIAGNOSTICS_REFRESH_MS);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            return;
        }
        if (workRequestsVisible()) {
            loadWorkRequests({force: true});
        }
        if (diagnosticsVisible()) {
            loadDiagnostics({force: true});
        }
    });

    const initialView = new URLSearchParams(window.location.search).get("view") || window.location.hash.replace("#", "") || "global-config";
    setActiveView(initialView);
    load();
})();
