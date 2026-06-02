(function () {
    const birdState = document.querySelector("#routing-bird-state");
    const birdVersion = document.querySelector("#routing-bird-version");
    const birdPid = document.querySelector("#routing-bird-pid");
    const birdUptime = document.querySelector("#routing-bird-uptime");
    const form = document.querySelector("#bird-global-settings-form");
    const status = document.querySelector("#bird-global-settings-status");
    const ripForm = document.querySelector("#bird-rip-settings-form");
    const ripStatus = document.querySelector("#bird-rip-settings-status");
    const bgpForm = document.querySelector("#bird-bgp-settings-form");
    const bgpStatus = document.querySelector("#bird-bgp-settings-status");
    const bgpInstancesBody = document.querySelector("#bird-bgp-instances-body");
    const bgpSubmitButton = document.querySelector("#bird-bgp-submit-button");
    const bgpCancelEditButton = document.querySelector("#bird-bgp-cancel-edit-button");
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
    const diagnosticsBody = document.querySelector("#bird-diagnostics-protocols-body");
    const diagnosticsTable = document.querySelector("#bird-diagnostics-table-wrap");
    const ripDiagnosticsBlocks = document.querySelector("#bird-rip-diagnostics-blocks");
    const ripRoutesBlocks = document.querySelector("#bird-rip-routes-blocks");
    const ripRoutesSummary = document.querySelector("#bird-rip-routes-summary");
    const ripRoutesFilter = document.querySelector("#bird-rip-routes-filter");
    const ripRoutesTableFilter = document.querySelector("#bird-rip-routes-table-filter");
    const diagnosticsOutput = document.querySelector("#bird-diagnostics-output");
    const viewButtons = Array.from(document.querySelectorAll("[data-routing-view]"));
    const WORK_REQUEST_REFRESH_MS = 3000;
    const DIAGNOSTICS_REFRESH_MS = 5000;
    const panels = {
        "global-config": document.querySelector("#routing-global-config-panel"),
        rip: document.querySelector("#routing-rip-panel"),
        "rip-routes": document.querySelector("#routing-rip-routes-panel"),
        ospf: document.querySelector("#routing-ospf-panel"),
        bgp: document.querySelector("#routing-bgp-panel"),
        "bgp-diagnostics": document.querySelector("#routing-bgp-diagnostics-panel"),
        "bgp-routes": document.querySelector("#routing-bgp-routes-panel"),
        logs: logsPanel,
        diagnostics: diagnosticsPanel,
        "work-requests": workRequestsPanel,
    };

    const fields = {
        router_id: document.querySelector("#bird-router-id"),
        hostname: document.querySelector("#bird-hostname"),
        debug_enabled: document.querySelector("#bird-debug-enabled"),
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
        bgp: {
            enabled: document.querySelector("#bird-bgp-enabled"),
            protocol_name: document.querySelector("#bird-bgp-protocol-name"),
            description: document.querySelector("#bird-bgp-description"),
            source_address: document.querySelector("#bird-bgp-source-address"),
            local_as: document.querySelector("#bird-bgp-local-as"),
            neighbor_ip: document.querySelector("#bird-bgp-neighbor-ip"),
            neighbor_as: document.querySelector("#bird-bgp-neighbor-as"),
            session_type: document.querySelector("#bird-bgp-session-type"),
            iface_name: document.querySelector("#bird-bgp-iface-name"),
            direct: document.querySelector("#bird-bgp-direct"),
            multihop: document.querySelector("#bird-bgp-multihop"),
            multihop_ttl: document.querySelector("#bird-bgp-multihop-ttl"),
            passive: document.querySelector("#bird-bgp-passive"),
            password: document.querySelector("#bird-bgp-password"),
            import_policy: document.querySelector("#bird-bgp-import-policy"),
            export_policy: document.querySelector("#bird-bgp-export-policy"),
        },
    };
    let currentServiceState = "";
    let routingSettingsContext = "global-config";
    let pendingAction = null;
    let logsLoading = false;
    let ripLoading = false;
    let ripSelectedInterfaceValues = ["*"];
    let ripEnabled = false;
    let bgpLoading = false;
    let bgpCurrentInstanceId = null;
    let bgpInterfacesCache = [];
    let bgpInstancesCache = [];
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

    function setBgpStatus(message, isError) {
        if (!bgpStatus) {
            return;
        }
        bgpStatus.textContent = message;
        bgpStatus.hidden = !message;
        bgpStatus.classList.toggle("error", Boolean(isError));
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

    function syncQueryActionButtons() {
        viewButtons.forEach((button) => {
            const view = button.dataset.routingView;
            const isBirdDiagnostics = routingSettingsContext === "global-config" && view === "diagnostics";
            const isRipDiagnostics = routingSettingsContext === "rip" && view === "diagnostics";
            const isRipRoutes = view === "rip-routes";
            const isBgpDiagnostics = routingSettingsContext === "bgp" && view === "bgp-diagnostics";
            const isBgpRoutes = routingSettingsContext === "bgp" && view === "bgp-routes";
            const birdStopped = currentServiceState !== "RUNNING";
            const shouldDisable = (isBirdDiagnostics && birdStopped) || ((birdStopped || !ripEnabled) && (isRipDiagnostics || isRipRoutes)) || (birdStopped && (isBgpDiagnostics || isBgpRoutes));
            button.setAttribute("aria-disabled", shouldDisable ? "true" : "false");
            button.classList.toggle("disabled", shouldDisable);
        });
    }

    function diagnosticsVisible() {
        return Boolean(diagnosticsPanel && !diagnosticsPanel.hidden);
    }

    function setRoutingNavigationContext(selectedView) {
        const unimplementedProtocol = selectedView === "ospf";
        if (selectedView === "rip" || selectedView === "rip-routes") {
            routingSettingsContext = "rip";
        } else if (selectedView === "bgp" || selectedView === "bgp-diagnostics" || selectedView === "bgp-routes") {
            routingSettingsContext = "bgp";
        } else if (selectedView !== "diagnostics") {
            routingSettingsContext = "global-config";
        }

        if (routingServiceActions) {
            routingServiceActions.hidden = unimplementedProtocol;
        }
        if (serviceActionTabs) {
            serviceActionTabs.hidden = routingSettingsContext === "rip" || routingSettingsContext === "bgp";
        }
        contextButtons.forEach((button) => {
            button.hidden = button.dataset.routingContextButton !== routingSettingsContext;
        });
        viewButtons.forEach((button) => {
            if (button.dataset.routingView === "diagnostics" && !button.dataset.routingContextButton) {
                button.hidden = routingSettingsContext === "bgp";
            }
        });
        syncQueryActionButtons();
    }

    function isRoutingButtonActive(button, selectedView) {
        if (button.dataset.routingView === selectedView) {
            return true;
        }
        return selectedView === "diagnostics" && button.dataset.routingView === "diagnostics";
    }

    function markRoutingContextButtonActive(context) {
        viewButtons.forEach((button) => {
            if (button.dataset.routingContextButton) {
                button.classList.toggle("active", button.dataset.routingContextButton === context);
                return;
            }
            if (button.dataset.routingView === "work-requests") {
                button.classList.remove("active");
            }
        });
    }

    function markSidebarRoutingView(view) {
        document.querySelectorAll('.menu-link[href^="/network/routing-protocols"]').forEach((link) => {
            const url = new URL(link.getAttribute("href"), window.location.origin);
            link.classList.toggle("active", url.searchParams.get("view") === view);
        });
        const url = new URL(window.location.href);
        url.searchParams.set("view", view);
        window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
    }

    function setActiveView(viewName) {
        let selectedView = panels[viewName] ? viewName : "global-config";
        if (routingSettingsContext === "rip" && !ripEnabled && (selectedView === "diagnostics" || selectedView === "rip-routes")) {
            selectedView = "rip";
        }
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
        if (selectedView === "bgp") {
            loadBgp();
        }
        if (selectedView === "rip-routes") {
            loadRipRoutes({force: true});
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
            actionConfirm.hidden = false;
        }
    }

    function openActionModal(action, label, run, title = "Confirm action", options = {}) {
        pendingAction = {action, run};
        if (actionTitle) {
            actionTitle.textContent = title;
        }
        if (actionMessage) {
            actionMessage.textContent = label;
        }
        if (actionConfirm) {
            actionConfirm.disabled = false;
            actionConfirm.hidden = Boolean(options.hideConfirm);
        }
        if (actionModal) {
            actionModal.hidden = false;
        }
    }

    function openInfoModal(label, title = "Information") {
        openActionModal("info", label, closeActionModal, title, {hideConfirm: true});
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

    function renderBgpInterfaceOptions(interfaces, bgpIface) {
        const select = fields.bgp.iface_name;
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
        setFieldValue(select, bgpIface || "");
    }

    function setBgpFormMode(isEditing) {
        if (bgpSubmitButton) {
            bgpSubmitButton.textContent = isEditing ? "Save" : "Add";
        }
        if (bgpCancelEditButton) {
            bgpCancelEditButton.hidden = !isEditing;
        }
    }

    function renderBgpInstances(instances) {
        bgpInstancesCache = Array.isArray(instances) ? instances.slice() : [];
        if (!bgpInstancesBody) {
            return;
        }
        if (!bgpInstancesCache.length) {
            bgpInstancesBody.innerHTML = `
                <tr>
                    <td colspan="9"><div class="terminal-empty"><span class="prompt">$</span><span>no bgp instances configured</span></div></td>
                </tr>
            `;
            return;
        }
        bgpInstancesBody.innerHTML = bgpInstancesCache.map((instance) => {
            const description = String(instance.description || "-");
            const truncatedDescription = description.length > 48 ? `${description.slice(0, 48)}...` : description;
            return `
                <tr>
                    <td>${HF.escapeHtml(instance.name || "-")}</td>
                    <td><span class="bgp-description-cell" title="${HF.escapeHtml(description)}">${HF.escapeHtml(truncatedDescription)}</span></td>
                    <td>${HF.escapeHtml(instance.neighbor_ip || "-")}</td>
                    <td>${HF.escapeHtml(instance.local_as || "-")}</td>
                    <td>${HF.escapeHtml(instance.neighbor_as || "-")}</td>
                    <td>${HF.escapeHtml(instance.import_policy || "none")}</td>
                    <td>${HF.escapeHtml(instance.export_policy || "none")}</td>
                    <td><span class="status ${instance.enabled ? "up" : "disabled"}">${instance.enabled ? "enabled" : "disabled"}</span></td>
                    <td>
                        <div class="table-actions">
                            <button class="text-button compact" type="button" data-bgp-instance-action="edit" data-bgp-instance-id="${HF.escapeHtml(instance.id)}">Edit</button>
                            <button class="text-button compact" type="button" data-bgp-instance-action="delete" data-bgp-instance-id="${HF.escapeHtml(instance.id)}">Delete</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
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
        setFieldValue(fields.debug_enabled, settings.debug_enabled);
        Object.entries(fields.kernel).forEach(([name, element]) => setFieldValue(element, kernel[name]));
        Object.entries(fields.device).forEach(([name, element]) => setFieldValue(element, device[name]));
        Object.entries(fields.direct).forEach(([name, element]) => setFieldValue(element, direct[name]));
    }

    function readForm() {
        return {
            router_id: readFieldValue(fields.router_id),
            hostname: readFieldValue(fields.hostname),
            debug_enabled: readFieldValue(fields.debug_enabled),
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

    function syncBgpTransportControls(source) {
        if (!fields.bgp.multihop || !fields.bgp.direct || !fields.bgp.multihop_ttl) {
            return;
        }
        if (source === "multihop" && fields.bgp.multihop.checked) {
            fields.bgp.direct.checked = false;
        }
        if (source === "direct" && fields.bgp.direct.checked) {
            fields.bgp.multihop.checked = false;
        }
        fields.bgp.multihop_ttl.disabled = !fields.bgp.multihop.checked;
        if (fields.bgp.iface_name) {
            fields.bgp.iface_name.disabled = fields.bgp.multihop.checked || !fields.bgp.direct.checked;
        }
    }

    function populateBgpForm(settings, interfaces) {
        const normalized = settings || {};
        bgpInterfacesCache = Array.isArray(interfaces) ? interfaces.slice() : bgpInterfacesCache;
        bgpCurrentInstanceId = normalized.id ?? null;
        Object.entries(fields.bgp).forEach(([name, element]) => setFieldValue(element, normalized[name]));
        renderBgpInterfaceOptions(bgpInterfacesCache || [], normalized.iface_name);
        syncBgpTransportControls();
        setBgpFormMode(bgpCurrentInstanceId !== null);
    }

    function resetBgpForm() {
        bgpCurrentInstanceId = null;
        populateBgpForm({
            enabled: false,
            description: "",
            local_as: "",
            neighbor_ip: "",
            neighbor_as: "",
            iface_name: "",
            session_type: "auto",
            direct: true,
            multihop: false,
            multihop_ttl: 64,
            passive: false,
            password: "",
            import_policy: "ipv4",
            export_policy: "none",
        }, bgpInterfacesCache || []);
        setBgpStatus("", false);
    }

    function validateBgpForm() {
        const sourceAddress = String(readFieldValue(fields.bgp.source_address) || "").trim();
        const neighborIp = String(readFieldValue(fields.bgp.neighbor_ip) || "").trim();
        const localAs = String(readFieldValue(fields.bgp.local_as) || "").trim();
        const neighborAs = String(readFieldValue(fields.bgp.neighbor_as) || "").trim();
        const ipPattern = /^(?:[0-9]{1,3}(?:\.[0-9]{1,3}){3}|[0-9A-Fa-f:]+)(?:\/(?:[0-9]{1,3}))?$/;
        const asPattern = /^\d+$/;

        if (sourceAddress && !ipPattern.test(sourceAddress)) {
            throw new Error("Source IP/Mask must be a valid IPv4 or IPv6 address.");
        }
        if (!neighborIp || !ipPattern.test(neighborIp)) {
            throw new Error("Neighbor IP/Mask must be a valid IPv4 or IPv6 address.");
        }
        if (!asPattern.test(localAs)) {
            throw new Error("Local AS must contain numbers only.");
        }
        if (!asPattern.test(neighborAs)) {
            throw new Error("Neighbor AS must contain numbers only.");
        }
    }

    function sanitizeBgpAsInput(event) {
        const element = event?.target;
        if (!element) {
            return;
        }
        element.value = String(element.value || "").replace(/\D+/g, "");
    }

    function sanitizeBgpAddressInput(event) {
        const element = event?.target;
        if (!element) {
            return;
        }
        element.value = String(element.value || "").replace(/[^0-9A-Fa-f:./]/g, "");
    }

    function allowBgpAddressBeforeInput(event) {
        const data = event?.data;
        if (!data) {
            return;
        }
        if (/^[0-9A-Fa-f:./]+$/.test(data)) {
            return;
        }
        event.preventDefault();
    }

    function sanitizeBgpAddressPaste(event) {
        const element = event?.target;
        const pasted = event?.clipboardData?.getData("text") || "";
        if (!element) {
            return;
        }
        const sanitized = pasted.replace(/[^0-9A-Fa-f:./]/g, "");
        if (sanitized === pasted) {
            return;
        }
        event.preventDefault();
        const start = element.selectionStart ?? element.value.length;
        const end = element.selectionEnd ?? element.value.length;
        const current = String(element.value || "");
        element.value = `${current.slice(0, start)}${sanitized}${current.slice(end)}`;
    }

    function readBgpForm() {
        return {
            enabled: readFieldValue(fields.bgp.enabled),
            protocol_name: readFieldValue(fields.bgp.protocol_name),
            description: readFieldValue(fields.bgp.description),
            source_address: readFieldValue(fields.bgp.source_address),
            local_as: readFieldValue(fields.bgp.local_as),
            neighbor_ip: readFieldValue(fields.bgp.neighbor_ip),
            neighbor_as: readFieldValue(fields.bgp.neighbor_as),
            iface_name: readFieldValue(fields.bgp.iface_name),
            session_type: readFieldValue(fields.bgp.session_type),
            direct: readFieldValue(fields.bgp.direct),
            multihop: readFieldValue(fields.bgp.multihop),
            multihop_ttl: readFieldValue(fields.bgp.multihop_ttl),
            passive: readFieldValue(fields.bgp.passive),
            password: readFieldValue(fields.bgp.password),
            import_policy: readFieldValue(fields.bgp.import_policy),
            export_policy: readFieldValue(fields.bgp.export_policy),
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
        syncQueryActionButtons();
    }

    let serviceSummaryLoading = false;
    async function load() {
        if (serviceSummaryLoading) {
            return;
        }
        serviceSummaryLoading = true;
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/global-settings");
            render(data);
        } catch (error) {
            setStatus(error.message, true);
        } finally {
            serviceSummaryLoading = false;
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
            ripEnabled = Boolean((data.settings || {}).enabled);
            syncQueryActionButtons();
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
            ripEnabled = Boolean((data.settings || {}).enabled);
            syncQueryActionButtons();
            populateRipForm(data.settings || {});
            setRipStatus("", false);
            await showWorkRequests();
            markSidebarRoutingView("global-config");
        } catch (error) {
            setRipStatus(error.message, true);
        }
    }

    async function loadBgp(instanceId = null) {
        if (bgpLoading) {
            return;
        }
        bgpLoading = true;
        try {
            const query = instanceId ? `?instance_id=${encodeURIComponent(instanceId)}` : "";
            const data = await HF.fetchJson(`/api/network/routing-protocols/bird/bgp-settings${query}`);
            renderBgpInstances(data.instances || []);
            populateBgpForm(data.settings || {}, data.interfaces || []);
            if (!instanceId && !(data.settings || {}).id) {
                resetBgpForm();
            }
            setBgpStatus("", false);
        } catch (error) {
            setBgpStatus(error.message, true);
        } finally {
            bgpLoading = false;
        }
    }

    function confirmSaveBgp(event) {
        event.preventDefault();
        try {
            validateBgpForm();
        } catch (error) {
            setBgpStatus(error.message, true);
            return;
        }
        const editing = bgpCurrentInstanceId !== null;
        openActionModal(
            editing ? "save-bgp-config" : "add-bgp-config",
            editing ? "Save this BGP instance?" : "Add this BGP instance?",
            saveBgpSettings,
            editing ? "Save configuration" : "Add configuration",
        );
    }

    async function saveBgpSettings() {
        const editing = bgpCurrentInstanceId !== null;
        setBgpStatus(editing ? "Saving BGP instance..." : "Adding BGP instance...", false);
        try {
            const endpoint = editing
                ? `/api/network/routing-protocols/bird/bgp-settings/${encodeURIComponent(bgpCurrentInstanceId)}`
                : "/api/network/routing-protocols/bird/bgp-settings";
            const method = editing ? "PUT" : "POST";
            const data = await HF.fetchJson(endpoint, {
                method,
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(readBgpForm()),
            });
            renderBgpInstances(data.instances || []);
            populateBgpForm(data.settings || {}, data.interfaces || []);
            if (!editing) {
                resetBgpForm();
            }
            setBgpStatus("", false);
            await showWorkRequests();
            markSidebarRoutingView("global-config");
        } catch (error) {
            setBgpStatus(error.message, true);
        }
    }

    function confirmDeleteBgpInstance(instanceId) {
        openActionModal(
            "delete-bgp-config",
            `Delete BGP instance bgp${HF.text(instanceId)}?`,
            () => deleteBgpInstance(instanceId),
            "Delete instance",
        );
    }

    async function deleteBgpInstance(instanceId) {
        setBgpStatus("Deleting BGP instance...", false);
        try {
            const data = await HF.fetchJson(`/api/network/routing-protocols/bird/bgp-settings/${encodeURIComponent(instanceId)}`, {
                method: "DELETE",
            });
            renderBgpInstances(data.instances || []);
            if (Number(bgpCurrentInstanceId) === Number(instanceId)) {
                resetBgpForm();
            }
            setBgpStatus("", false);
            await showWorkRequests();
            markSidebarRoutingView("global-config");
        } catch (error) {
            setBgpStatus(error.message, true);
        }
    }

    async function runServiceAction(action) {
        const sourceContext = routingSettingsContext;
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
        if (sourceContext === "rip") {
            markRoutingContextButtonActive("global-config");
        }
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

    function setDiagnosticsSummary(run) {
        const collectedAt = run?.collected_at || "";
        if (!diagnosticsSummary) {
            return;
        }
        if (collectedAt) {
            diagnosticsSummary.innerHTML = `Live / <span class="refresh-state-label">updated=</span>${HF.escapeHtml(collectedAt)}`;
            return;
        }
        diagnosticsSummary.textContent = "No snapshot";
    }

    function renderBirdDiagnostics(data) {
        const run = data.last_run;
        const protocols = data.protocols || [];
        if (diagnosticsTable) {
            diagnosticsTable.hidden = false;
        }
        if (ripDiagnosticsBlocks) {
            ripDiagnosticsBlocks.hidden = true;
            ripDiagnosticsBlocks.innerHTML = "";
        }
        if (diagnosticsOutput) {
            diagnosticsOutput.hidden = true;
            diagnosticsOutput.textContent = "";
        }
        setDiagnosticsSummary(run);
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
    }

    function captureScrollState(container) {
        const outputScroll = {};
        container?.querySelectorAll(".routing-diagnostics-output").forEach((element, index) => {
            outputScroll[index] = element.scrollTop;
        });
        return {
            pageX: window.scrollX,
            pageY: window.scrollY,
            mainTop: document.querySelector("#main-content")?.scrollTop ?? null,
            outputScroll,
        };
    }

    function restoreScrollState(container, state) {
        container?.querySelectorAll(".routing-diagnostics-output").forEach((element, index) => {
            element.scrollTop = state.outputScroll[index] || 0;
        });
        if (state.mainTop !== null) {
            document.querySelector("#main-content")?.scrollTo({top: state.mainTop, behavior: "auto"});
        }
        window.scrollTo(state.pageX, state.pageY);
    }

    function renderRipDiagnostics(data) {
        const sections = (data.sections || []).filter((section) => section.key === "status");
        const scrollState = captureScrollState(ripDiagnosticsBlocks);
        setDiagnosticsSummary(data.last_run);
        if (diagnosticsTable) {
            diagnosticsTable.hidden = true;
        }
        if (diagnosticsOutput) {
            diagnosticsOutput.hidden = true;
            diagnosticsOutput.textContent = "";
        }
        if (!ripDiagnosticsBlocks) {
            return;
        }
        ripDiagnosticsBlocks.hidden = false;
        if (!sections.length) {
            ripDiagnosticsBlocks.innerHTML = `<pre class="tool-output routing-diagnostics-output routing-empty-output"></pre>`;
            restoreScrollState(ripDiagnosticsBlocks, scrollState);
            return;
        }
        ripDiagnosticsBlocks.innerHTML = sections.map((section) => {
            const output = (section.raw_output || section.error_output || "No output collected.").trim() || "No output collected.";
            return `<pre class="tool-output routing-diagnostics-output">${HF.escapeHtml(section.command || "")}
${HF.escapeHtml(output)}</pre>`;
        }).join("");
        restoreScrollState(ripDiagnosticsBlocks, scrollState);
    }

    function currentRipRouteSection(data) {
        const selectedRouteView = ripRoutesFilter?.value || "learned_routes";
        return (data.sections || []).find((section) => section.key === selectedRouteView) || null;
    }

    function renderRipRouteTableOptions(routes) {
        if (!ripRoutesTableFilter) {
            return;
        }
        const previous = ripRoutesTableFilter.value;
        const tableNames = Array.from(new Set((routes || []).map((route) => route.table_name || "-").filter(Boolean))).sort();
        ripRoutesTableFilter.innerHTML = "";
        ripRoutesTableFilter.hidden = tableNames.length === 0;
        tableNames.forEach((tableName) => {
            ripRoutesTableFilter.appendChild(option(tableName, tableName));
        });
        if (tableNames.includes(previous)) {
            setFieldValue(ripRoutesTableFilter, previous);
        } else if (tableNames.length) {
            setFieldValue(ripRoutesTableFilter, tableNames[0]);
        }
        ripRoutesTableFilter.disabled = tableNames.length <= 1;
    }

    let ripRoutesData = null;
    function renderRipRouteBlocks(data) {
        ripRoutesData = data;
        const section = currentRipRouteSection(data);
        const sections = section ? [section] : [];
        if (ripRoutesSummary) {
            ripRoutesSummary.textContent = "";
        }
        if (!ripRoutesBlocks) {
            return;
        }
        if (!sections.length) {
            ripRoutesBlocks.innerHTML = "";
            renderRipRouteTableOptions([]);
            return;
        }
        ripRoutesBlocks.innerHTML = sections.map((section) => {
            const allRoutes = section.routes || [];
            renderRipRouteTableOptions(allRoutes);
            const selectedTable = ripRoutesTableFilter?.value || "";
            const routes = selectedTable ? allRoutes.filter((route) => (route.table_name || "-") === selectedTable) : allRoutes;
            if (!routes.length) {
                return `<div class="terminal-empty"><span class="prompt">$</span><span>No structured routes collected.</span></div>`;
            }
            return `
                <div class="table-wrap routing-routes-table-wrap">
                    <table class="data-table routing-routes-table">
                        <thead>
                            <tr>
                                <th>Table</th>
                                <th>Prefix</th>
                                <th>Type</th>
                                <th>Source</th>
                                <th>Metric</th>
                                <th>Next Hop</th>
                                <th>Interface</th>
                                <th>Since</th>
                                <th>Selected</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${routes.map((route) => `
                                <tr>
                                    <td>${HF.escapeHtml(route.table_name || "-")}</td>
                                    <td>${HF.escapeHtml(route.route_prefix || "-")}</td>
                                    <td>${HF.escapeHtml(route.route_type || "-")}</td>
                                    <td>${HF.escapeHtml(route.source_protocol || "-")}</td>
                                    <td>${HF.escapeHtml(route.metric ?? "-")}</td>
                                    <td>${HF.escapeHtml(route.next_hop || "-")}</td>
                                    <td>${HF.escapeHtml(route.iface_name || "-")}</td>
                                    <td>${HF.escapeHtml(route.since || "-")}</td>
                                    <td>${route.selected ? "yes" : "no"}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
            `;
        }).join("");
    }

    let ripRoutesLoading = false;
    async function loadRipRoutes(options = {}) {
        if (!panels["rip-routes"] || panels["rip-routes"].hidden) {
            return;
        }
        if (ripRoutesLoading && !options.force) {
            return;
        }
        ripRoutesLoading = true;
        try {
            renderRipRouteBlocks(await HF.fetchJson("/api/network/routing-protocols/bird/rip-diagnostics"));
        } catch (error) {
            if (ripRoutesBlocks) {
                ripRoutesBlocks.innerHTML = `<div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>`;
            }
        } finally {
            ripRoutesLoading = false;
        }
    }

    function renderDiagnostics(data) {
        if (routingSettingsContext === "rip") {
            renderRipDiagnostics(data);
            return;
        }
        renderBirdDiagnostics(data);
    }

    let headerDiagnosticsLoading = false;
    async function loadHeaderDiagnostics(options = {}) {
        if (!diagnosticsSummary) {
            return;
        }
        if (headerDiagnosticsLoading && !options.force) {
            return;
        }
        headerDiagnosticsLoading = true;
        try {
            const data = await HF.fetchJson("/api/network/routing-protocols/bird/diagnostics");
            setDiagnosticsSummary(data.last_run);
        } catch (error) {
            diagnosticsSummary.textContent = "Error";
        } finally {
            headerDiagnosticsLoading = false;
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
            const endpoint = routingSettingsContext === "rip"
                ? "/api/network/routing-protocols/bird/rip-diagnostics"
                : "/api/network/routing-protocols/bird/diagnostics";
            renderDiagnostics(await HF.fetchJson(endpoint));
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
            await load();
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
        button.addEventListener("click", () => {
            const view = button.dataset.routingView || "global-config";
            if (button.getAttribute("aria-disabled") === "true") {
                if (currentServiceState !== "RUNNING") {
                    openInfoModal("BIRD daemon is not running. Start BIRD before opening Diagnostics or Show Routes.", "BIRD stopped");
                    return;
                }
                openInfoModal("RIP protocol is disabled. Enable RIP Settings before opening Diagnostics or Show Routes.", "RIP disabled");
                return;
            }
            setActiveView(view);
        });
    });
    if (form) {
        form.addEventListener("submit", confirmSave);
    }
    if (ripForm) {
        ripForm.addEventListener("submit", confirmSaveRip);
    }
    if (bgpForm) {
        bgpForm.addEventListener("submit", confirmSaveBgp);
    }
    if (bgpCancelEditButton) {
        bgpCancelEditButton.addEventListener("click", resetBgpForm);
    }
    if (fields.bgp.multihop) {
        fields.bgp.multihop.addEventListener("change", () => syncBgpTransportControls("multihop"));
    }
    if (fields.bgp.direct) {
        fields.bgp.direct.addEventListener("change", () => syncBgpTransportControls("direct"));
    }
    if (fields.bgp.local_as) {
        fields.bgp.local_as.addEventListener("input", sanitizeBgpAsInput);
    }
    if (fields.bgp.neighbor_as) {
        fields.bgp.neighbor_as.addEventListener("input", sanitizeBgpAsInput);
    }
    if (fields.bgp.source_address) {
        fields.bgp.source_address.addEventListener("beforeinput", allowBgpAddressBeforeInput);
        fields.bgp.source_address.addEventListener("paste", sanitizeBgpAddressPaste);
        fields.bgp.source_address.addEventListener("input", sanitizeBgpAddressInput);
    }
    if (fields.bgp.neighbor_ip) {
        fields.bgp.neighbor_ip.addEventListener("beforeinput", allowBgpAddressBeforeInput);
        fields.bgp.neighbor_ip.addEventListener("paste", sanitizeBgpAddressPaste);
        fields.bgp.neighbor_ip.addEventListener("input", sanitizeBgpAddressInput);
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
        const bgpActionButton = event.target.closest("[data-bgp-instance-action]");
        if (bgpActionButton) {
            const action = bgpActionButton.dataset.bgpInstanceAction;
            const instanceId = Number(bgpActionButton.dataset.bgpInstanceId || 0);
            if (!instanceId) {
                return;
            }
            if (action === "edit") {
                loadBgp(instanceId);
                return;
            }
            if (action === "delete") {
                confirmDeleteBgpInstance(instanceId);
                return;
            }
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
    if (ripRoutesFilter) {
        ripRoutesFilter.addEventListener("change", () => {
            if (ripRoutesData) {
                renderRipRouteBlocks(ripRoutesData);
                return;
            }
            loadRipRoutes({force: true});
        });
    }
    if (ripRoutesTableFilter) {
        ripRoutesTableFilter.addEventListener("change", () => {
            if (ripRoutesData) {
                renderRipRouteBlocks(ripRoutesData);
            }
        });
    }
    window.setInterval(() => {
        if (workRequestsVisible()) {
            loadWorkRequests();
        }
    }, WORK_REQUEST_REFRESH_MS);
    window.setInterval(() => {
        loadHeaderDiagnostics();
        if (diagnosticsVisible()) {
            loadDiagnostics();
        }
        if (logsPanel && !logsPanel.hidden) {
            loadLogs();
        }
        if (panels["rip-routes"] && !panels["rip-routes"].hidden) {
            loadRipRoutes();
        }
    }, DIAGNOSTICS_REFRESH_MS);
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            return;
        }
        loadHeaderDiagnostics({force: true});
        if (workRequestsVisible()) {
            loadWorkRequests({force: true});
        }
        if (diagnosticsVisible()) {
            loadDiagnostics({force: true});
        }
        if (logsPanel && !logsPanel.hidden) {
            loadLogs();
        }
        if (panels["rip-routes"] && !panels["rip-routes"].hidden) {
            loadRipRoutes({force: true});
        }
    });

    const initialView = new URLSearchParams(window.location.search).get("view") || window.location.hash.replace("#", "") || "global-config";
    setActiveView(initialView);
    load();
    loadHeaderDiagnostics({force: true});
})();
