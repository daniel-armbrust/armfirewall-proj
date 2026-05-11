(function () {
    const stateLabel = document.querySelector("#linkfailover-state");
    const settingsForm = document.querySelector("#linkfailover-settings-form");
    const linkForm = document.querySelector("#linkfailover-link-form");
    const linksBody = document.querySelector("#linkfailover-links-body");
    const linksCount = document.querySelector("#linkfailover-links-count");
    const eventsBody = document.querySelector("#linkfailover-events-body");
    const eventsCount = document.querySelector("#linkfailover-events-count");
    const ifaceSelect = document.querySelector("#linkfailover-iface");
    const formStatus = document.querySelector("#linkfailover-form-status");
    const submitButton = document.querySelector("#linkfailover-link-submit");
    const linksPanel = document.querySelector("#linkfailover-links-panel");
    const newLinkPanel = document.querySelector("#linkfailover-new-link-panel");
    const eventsPanel = document.querySelector("#linkfailover-events-panel");
    const workRequestsPanel = document.querySelector("#linkfailover-work-requests-panel");
    const workRequestsBody = document.querySelector("#linkfailover-work-requests-body");
    const workRequestsCount = document.querySelector("#linkfailover-work-requests-count");
    const viewButtons = Array.from(document.querySelectorAll("[data-linkfailover-view]"));
    const modal = document.querySelector("#linkfailover-action-modal");
    const modalMessage = document.querySelector("#linkfailover-action-message");
    const modalConfirm = document.querySelector("[data-linkfailover-modal-confirm]");
    const applyButton = document.querySelector("#linkfailover-apply");
    const settingsStatus = document.querySelector("#linkfailover-settings-status");
    let latestConfig = {links: [], interfaces: []};
    let pendingAction = null;
    let settingsDirty = false;
    let loading = false;
    let workRequestsLoading = false;
    const POLL_MS = 5000;

    function setSettingsDirty(value) {
        settingsDirty = Boolean(value);
        if (applyButton) {
            applyButton.hidden = !settingsDirty;
        }
        if (settingsStatus && settingsDirty) {
            settingsStatus.hidden = true;
            settingsStatus.textContent = "";
        }
    }

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
        if (text === "healthy" || text === "success") {
            return "up";
        }
        if (text === "failed") {
            return "down";
        }
        return "disabled";
    }

    function interfaceLabel(ifaceName) {
        const iface = (latestConfig.interfaces || []).find((item) => item.name === ifaceName);
        if (!iface) {
            return ifaceName;
        }
        const role = iface.role || "UNKNOWN";
        const desc = iface.description || "";
        return `${iface.name} (${role})${desc ? ` - ${desc}` : ""}`;
    }

    function interfaceTooltip(ifaceName) {
        const iface = (latestConfig.interfaces || []).find((item) => item.name === ifaceName);
        if (!iface) {
            return HF.escapeHtml(ifaceName);
        }
        const addresses = (iface.addresses || []).map((item) => `${item.addr}/${item.prefixlen}`).join(", ");
        return HF.escapeHtml([
            `Interface: ${iface.name}`,
            `Role: ${iface.role || "UNKNOWN"}`,
            `Description: ${iface.description || "-"}`,
            `MAC: ${iface.mac_address || "-"}`,
            `Addresses: ${addresses || "-"}`,
        ].join("\n"));
    }

    function renderInterfaceChoices(interfaces) {
        if (!ifaceSelect) {
            return;
        }
        ifaceSelect.innerHTML = interfaces.map((iface) => `
            <option value="${HF.escapeHtml(iface.name)}">${HF.escapeHtml(interfaceLabel(iface.name))}</option>
        `).join("");
    }

    function renderLinks(links) {
        if (linksCount) {
            linksCount.textContent = `links=${links.length}`;
        }
        if (!linksBody) {
            return;
        }
        if (!links.length) {
            linksBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no failover links configured</span></div></td>
                </tr>
            `;
            return;
        }
        linksBody.innerHTML = links.map((link) => {
            return `
                <tr>
                    <td><span class="hf-tooltip" data-tooltip="${interfaceTooltip(link.iface)}"><strong>${HF.escapeHtml(link.iface)}</strong></span></td>
                    <td>${HF.escapeHtml(link.priority)}</td>
                    <td><span class="status ${statusClass(link.status)}">${HF.escapeHtml(link.status)}</span></td>
                    <td>${link.last_latency_ms === null || link.last_latency_ms === undefined ? "-" : `${HF.escapeHtml(Number(link.last_latency_ms).toFixed(3))} ms`}</td>
                    <td>
                        <button class="text-button compact" type="button" data-linkfailover-edit="${HF.escapeHtml(link.id)}">Edit</button>
                        <button class="text-button compact danger" type="button" data-linkfailover-delete="${HF.escapeHtml(link.id)}">Delete</button>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function updateNewLinkPanel() {
        if (!newLinkPanel) {
            return;
        }
        const editing = Boolean(document.querySelector("#linkfailover-link-id")?.value);
        newLinkPanel.hidden = !editing && (latestConfig.links || []).length >= 2;
    }

    function renderEvents(events) {
        if (eventsCount) {
            eventsCount.textContent = `events=${events.length}`;
        }
        if (!eventsBody) {
            return;
        }
        if (!events.length) {
            eventsBody.innerHTML = `
                <tr>
                    <td colspan="3"><div class="terminal-empty"><span class="prompt">$</span><span>no failover events</span></div></td>
                </tr>
            `;
            return;
        }
        eventsBody.innerHTML = events.map((event) => `
            <tr>
                <td>${HF.escapeHtml(event.created_at)}</td>
                <td><span class="status ${statusClass(event.event_type)}">${HF.escapeHtml(event.event_type)}</span></td>
                <td>${HF.escapeHtml(event.message)}</td>
            </tr>
        `).join("");
    }

    function renderConfig(data) {
        latestConfig = data;
        const settings = data.settings || {};
        const summary = data.summary || {};
        const interfaces = data.interfaces || [];
        const links = data.links || [];
        if (!settingsDirty) {
            document.querySelector("#linkfailover-target").value = settings.target || "registro.br";
            document.querySelector("#linkfailover-timeout").value = settings.timeout_seconds || 3;
            document.querySelector("#linkfailover-attempts").value = settings.attempts || 3;
            document.querySelector("#linkfailover-interval").value = settings.interval_seconds || 1;
            document.querySelector("#linkfailover-max-latency").value = settings.max_latency_ms ?? "";
            document.querySelector("#linkfailover-check-interval").value = settings.check_interval_seconds || 10;
        }
        setMetric("#linkfailover-summary-links", summary.links);
        setMetric("#linkfailover-summary-healthy", summary.healthy_links);
        setMetric("#linkfailover-summary-active", settings.current_iface || "-");
        renderInterfaceChoices(interfaces);
        renderLinks(links);
        renderEvents(data.events || []);
        updateNewLinkPanel();
        setState("Live", summary.updated_at || "-");
    }

    async function loadConfig() {
        if (loading) {
            return;
        }
        loading = true;
        try {
            setState("Polling");
            renderConfig(await HF.fetchJson("/api/services/link-failover"));
            if (workRequestsPanel && !workRequestsPanel.hidden) {
                await loadWorkRequests();
            }
        } catch (error) {
            setState("Offline");
            if (linksBody) {
                linksBody.innerHTML = `
                    <tr>
                        <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
        } finally {
            loading = false;
        }
    }

    function linkPayload() {
        return {
            iface: document.querySelector("#linkfailover-iface").value,
            priority: Number(document.querySelector("#linkfailover-priority").value || 100),
        };
    }

    function clearLinkForm() {
        document.querySelector("#linkfailover-link-id").value = "";
        if (ifaceSelect && ifaceSelect.options.length) {
            ifaceSelect.selectedIndex = 0;
        }
        document.querySelector("#linkfailover-priority").value = "100";
        if (submitButton) {
            submitButton.textContent = "Add link";
        }
        if (formStatus) {
            formStatus.hidden = true;
            formStatus.textContent = "";
        }
        updateNewLinkPanel();
    }

    function editLink(linkId) {
        const link = (latestConfig.links || []).find((item) => Number(item.id) === Number(linkId));
        if (!link) {
            return;
        }
        document.querySelector("#linkfailover-link-id").value = link.id;
        document.querySelector("#linkfailover-iface").value = link.iface;
        document.querySelector("#linkfailover-priority").value = link.priority;
        if (submitButton) {
            submitButton.textContent = "Save link";
        }
        updateNewLinkPanel();
        linkForm?.scrollIntoView({behavior: "smooth", block: "start"});
    }

    async function saveSettings(event) {
        event.preventDefault();
        if (!settingsDirty) {
            return;
        }
        if (applyButton) {
            applyButton.disabled = true;
        }
        try {
            await HF.fetchJson("/api/services/link-failover/settings", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    target: document.querySelector("#linkfailover-target").value,
                    timeout_seconds: Number(document.querySelector("#linkfailover-timeout").value || 3),
                    attempts: Number(document.querySelector("#linkfailover-attempts").value || 3),
                    interval_seconds: Number(document.querySelector("#linkfailover-interval").value || 1),
                    max_latency_ms: document.querySelector("#linkfailover-max-latency").value,
                    check_interval_seconds: Number(document.querySelector("#linkfailover-check-interval").value || 10),
                }),
            });
            setSettingsDirty(false);
            if (settingsStatus) {
                settingsStatus.hidden = false;
                settingsStatus.textContent = "Settings applied.";
            }
            await loadConfig();
        } catch (error) {
            if (settingsStatus) {
                settingsStatus.hidden = false;
                settingsStatus.textContent = error.message;
            }
        } finally {
            if (applyButton) {
                applyButton.disabled = false;
            }
        }
    }

    async function saveLink(event) {
        event.preventDefault();
        const linkId = document.querySelector("#linkfailover-link-id").value;
        if (!linkId && (latestConfig.links || []).length >= 2) {
            if (formStatus) {
                formStatus.hidden = false;
                formStatus.textContent = "Link Failover supports exactly two links.";
            }
            updateNewLinkPanel();
            return;
        }
        const url = linkId ? `/api/services/link-failover/links/${encodeURIComponent(linkId)}` : "/api/services/link-failover/links";
        const method = linkId ? "PUT" : "POST";
        try {
            await HF.fetchJson(url, {
                method,
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(linkPayload()),
            });
            clearLinkForm();
            await loadConfig();
        } catch (error) {
            if (formStatus) {
                formStatus.hidden = false;
                formStatus.textContent = error.message;
            }
        }
    }

    function openModal(action, payload) {
        pendingAction = {action, payload};
        if (modalMessage) {
            modalMessage.textContent = payload.message;
        }
        if (modal) {
            modal.hidden = false;
        }
    }

    function closeModal() {
        pendingAction = null;
        if (modal) {
            modal.hidden = true;
        }
    }

    async function confirmModal() {
        if (!pendingAction) {
            return;
        }
        const {action, payload} = pendingAction;
        modalConfirm.disabled = true;
        try {
            if (action === "delete") {
                await HF.fetchJson(`/api/services/link-failover/links/${encodeURIComponent(payload.id)}`, {method: "DELETE"});
                await loadConfig();
            }
            if (action === "service") {
                await HF.fetchJson("/api/services/status/armfirewall-linkfailover/action", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({action: payload.serviceAction}),
                });
                setActiveView("work-requests");
                await loadWorkRequests();
                document.querySelector("#main-content")?.scrollTo({top: 0, behavior: "smooth"});
                window.scrollTo({top: 0, behavior: "smooth"});
            }
            closeModal();
        } catch (error) {
            if (modalMessage) {
                modalMessage.textContent = error.message;
            }
        } finally {
            modalConfirm.disabled = false;
        }
    }

    function setActiveView(viewName) {
        const showWorkRequests = viewName === "work-requests";
        const showEvents = viewName === "events";
        if (linksPanel) {
            linksPanel.hidden = showWorkRequests || showEvents;
        }
        if (eventsPanel) {
            eventsPanel.hidden = !showEvents;
        }
        if (workRequestsPanel) {
            workRequestsPanel.hidden = !showWorkRequests;
        }
        viewButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.linkfailoverView === viewName);
        });
        if (showWorkRequests) {
            loadWorkRequests();
        } else {
            loadConfig();
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
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no link failover work requests</span></div></td>
                </tr>
            `;
            return;
        }
        workRequestsBody.innerHTML = requests.map((request) => `
            <tr>
                <td>${HF.escapeHtml(request.id)}</td>
                <td><span class="status ${statusClass(request.status)}">${HF.escapeHtml(request.status)}</span></td>
                <td>${HF.escapeHtml(request.action_name)}</td>
                <td>${HF.escapeHtml(request.updated_at)}</td>
                <td>${HF.escapeHtml(request.error_message || "")}</td>
            </tr>
        `).join("");
    }

    async function loadWorkRequests() {
        if (workRequestsLoading || !workRequestsPanel || workRequestsPanel.hidden) {
            return;
        }
        workRequestsLoading = true;
        try {
            renderWorkRequests(await HF.fetchJson("/api/services/link-failover/work-requests"));
        } finally {
            workRequestsLoading = false;
        }
    }

    document.addEventListener("click", (event) => {
        const editButton = event.target.closest("[data-linkfailover-edit]");
        if (editButton) {
            editLink(editButton.dataset.linkfailoverEdit);
            return;
        }
        const deleteButton = event.target.closest("[data-linkfailover-delete]");
        if (deleteButton) {
            openModal("delete", {id: deleteButton.dataset.linkfailoverDelete, message: "Delete this Link Failover entry?"});
            return;
        }
        const serviceButton = event.target.closest("[data-linkfailover-service-action]");
        if (serviceButton) {
            const serviceAction = serviceButton.dataset.linkfailoverServiceAction;
            openModal("service", {serviceAction, message: `${serviceAction.toUpperCase()} armfirewall-linkfailover?`});
            return;
        }
        const viewButton = event.target.closest("[data-linkfailover-view]");
        if (viewButton) {
            setActiveView(viewButton.dataset.linkfailoverView || "links");
            return;
        }
        if (event.target.closest("[data-linkfailover-modal-cancel]")) {
            closeModal();
        }
    });

    if (settingsForm) {
        settingsForm.addEventListener("submit", saveSettings);
        settingsForm.addEventListener("input", () => setSettingsDirty(true));
        settingsForm.addEventListener("change", () => setSettingsDirty(true));
    }
    if (linkForm) {
        linkForm.addEventListener("submit", saveLink);
    }
    if (modalConfirm) {
        modalConfirm.addEventListener("click", confirmModal);
    }

    setSettingsDirty(false);
    setActiveView("links");
    setInterval(loadConfig, POLL_MS);
    setInterval(loadWorkRequests, POLL_MS);
}());
