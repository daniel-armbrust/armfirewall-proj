(function () {
    const stateLabel = document.querySelector("#libreswan-state");
    const connectionsPanel = document.querySelector("#libreswan-connections-panel");
    const formPanel = document.querySelector("#libreswan-form-panel");
    const logsPanel = document.querySelector("#libreswan-logs-panel");
    const workRequestsPanel = document.querySelector("#libreswan-work-requests-panel");
    const connectionsBody = document.querySelector("#libreswan-connections-body");
    const connectionsCount = document.querySelector("#libreswan-connections-count");
    const logsCount = document.querySelector("#libreswan-logs-count");
    const logsOutput = document.querySelector("#libreswan-logs-output");
    const workRequestsBody = document.querySelector("#libreswan-work-requests-body");
    const workRequestsCount = document.querySelector("#libreswan-work-requests-count");
    const form = document.querySelector("#libreswan-form");
    const formTitle = document.querySelector("#libreswan-form-title");
    const formState = document.querySelector("#libreswan-form-state");
    const formStatus = document.querySelector("#libreswan-form-status");
    const submitButton = document.querySelector("#libreswan-submit");
    const clearButton = document.querySelector("#libreswan-clear");
    const secretGenerateButton = document.querySelector("#libreswan-secret-generate");
    const secretToggleButton = document.querySelector("#libreswan-secret-toggle");
    const viewButtons = Array.from(document.querySelectorAll("[data-libreswan-view]"));
    const serviceActionButtons = Array.from(document.querySelectorAll("[data-libreswan-service-action]"));
    let latestConnections = [];
    let interfaceInventory = [];
    let loading = false;
    let logsLoading = false;
    let workRequestsLoading = false;
    const POLL_MS = 5000;
    const LOG_POLL_MS = 10000;

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

    function ipsecStatusClass(status) {
        return String(status || "").toLowerCase() === "up" ? "up" : "down";
    }

    function ipsecStatusLabel(status) {
        return String(status || "").toLowerCase() === "up" ? "IPSec Up" : "IPSec Down";
    }

    function workRequestStatusClass(status) {
        const value = String(status || "").toLowerCase();
        if (value === "success") {
            return "up";
        }
        if (value === "failed") {
            return "down";
        }
        return "disabled";
    }

    function setActiveView(viewName) {
        const isForm = viewName === "new-connection";
        const isLogs = viewName === "logs";
        const isWorkRequests = viewName === "work-requests";
        if (connectionsPanel) {
            connectionsPanel.hidden = isForm || isLogs || isWorkRequests;
        }
        if (formPanel) {
            formPanel.hidden = !isForm;
        }
        if (logsPanel) {
            logsPanel.hidden = !isLogs;
        }
        if (workRequestsPanel) {
            workRequestsPanel.hidden = !isWorkRequests;
        }
        viewButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.libreswanView === viewName);
        });
        if (isLogs) {
            loadLogs();
        }
        if (isWorkRequests) {
            loadWorkRequests();
        }
    }

    function field(id) {
        return document.querySelector(`#${id}`);
    }

    function setSelectValue(id, value) {
        const element = field(id);
        if (!element) {
            return;
        }
        const selectedValue = value || "";
        if (selectedValue && !Array.from(element.options).some((option) => option.value === selectedValue)) {
            element.appendChild(new Option(selectedValue, selectedValue));
        }
        element.value = selectedValue;
    }

    function sharedSecretField() {
        return field("libreswan-shared-secret");
    }

    function setSharedSecretVisible(visible) {
        const element = sharedSecretField();
        if (!element || !secretToggleButton) {
            return;
        }
        element.type = visible ? "text" : "password";
        secretToggleButton.setAttribute("aria-pressed", visible ? "true" : "false");
        secretToggleButton.setAttribute("aria-label", visible ? "Hide shared secret" : "Show shared secret");
        secretToggleButton.setAttribute("title", visible ? "Hide shared secret" : "Show shared secret");
        secretToggleButton.textContent = visible ? "◌" : "◉";
    }

    function randomSharedSecret(length = 48) {
        const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789_-+=.:";
        const bytes = new Uint8Array(length);
        if (window.crypto?.getRandomValues) {
            window.crypto.getRandomValues(bytes);
        } else {
            for (let index = 0; index < bytes.length; index += 1) {
                bytes[index] = Math.floor(Math.random() * 256);
            }
        }
        return Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
    }

    function generateSharedSecret() {
        const element = sharedSecretField();
        if (!element) {
            return;
        }
        element.value = randomSharedSecret();
        element.focus();
        setSharedSecretVisible(true);
    }

    function normalizeIpv4Input(value) {
        return String(value || "")
            .replace(/[^\d.]/g, "")
            .replace(/\.{2,}/g, ".")
            .split(".")
            .slice(0, 4)
            .map((octet) => octet.slice(0, 3))
            .join(".");
    }

    function normalizeIpv4CidrInput(value) {
        const filtered = String(value || "").replace(/[^\d./]/g, "");
        const slashIndex = filtered.indexOf("/");
        const addressPart = slashIndex >= 0 ? filtered.slice(0, slashIndex) : filtered;
        const maskPart = slashIndex >= 0 ? filtered.slice(slashIndex + 1).replace(/\D/g, "").slice(0, 2) : "";
        const normalizedAddress = normalizeIpv4Input(addressPart);

        if (slashIndex < 0) {
            return normalizedAddress;
        }

        if (!maskPart) {
            return `${normalizedAddress}/`;
        }

        const mask = Math.min(Number(maskPart), 32);
        return `${normalizedAddress}/${mask}`;
    }

    function validIpv4Address(value) {
        const parts = String(value || "").split(".");
        return parts.length === 4 && parts.every((part) => {
            if (!/^\d{1,3}$/.test(part)) {
                return false;
            }
            const number = Number(part);
            return number >= 0 && number <= 255;
        });
    }

    function validIpv4Cidr(value) {
        const trimmed = String(value || "").trim();
        if (!trimmed) {
            return true;
        }
        const parts = trimmed.split("/");
        if (parts.length !== 2 || !validIpv4Address(parts[0]) || !/^\d{1,2}$/.test(parts[1])) {
            return false;
        }
        const mask = Number(parts[1]);
        return mask >= 0 && mask <= 32;
    }

    function setIpv4Validity(element) {
        const valid = validIpv4Address(element.value);
        element.classList.toggle("is-invalid", !valid && Boolean(element.value));
        element.setCustomValidity(valid ? "" : "Use a valid IPv4 address.");
        return valid;
    }

    function setIpv4CidrValidity(element) {
        const valid = validIpv4Cidr(element.value);
        element.classList.toggle("is-invalid", !valid && Boolean(element.value));
        element.setCustomValidity(valid ? "" : "Use a valid IPv4 address and mask.");
        return valid;
    }

    function normalizeIpv4Field(element) {
        const cursor = element.selectionStart;
        const before = element.value;
        element.value = normalizeIpv4Input(element.value);
        if (cursor !== null && before !== element.value) {
            const nextCursor = Math.min(cursor, element.value.length);
            element.setSelectionRange(nextCursor, nextCursor);
        }
        setIpv4Validity(element);
    }

    function normalizeIpv4CidrField(element) {
        const cursor = element.selectionStart;
        const before = element.value;
        element.value = normalizeIpv4CidrInput(element.value);
        if (cursor !== null && before !== element.value) {
            const nextCursor = Math.min(cursor, element.value.length);
            element.setSelectionRange(nextCursor, nextCursor);
        }
        setIpv4CidrValidity(element);
    }

    function validateIpv4Fields() {
        const ipv4Fields = Array.from(document.querySelectorAll("[data-ipv4-address]"));
        const invalidField = ipv4Fields.find((element) => !setIpv4Validity(element));
        if (invalidField) {
            invalidField.reportValidity();
            invalidField.focus();
            return false;
        }
        return true;
    }

    function validateIpv4CidrFields() {
        const cidrFields = Array.from(document.querySelectorAll("[data-ipv4-cidr]"));
        const invalidField = cidrFields.find((element) => !setIpv4CidrValidity(element));
        if (invalidField) {
            invalidField.reportValidity();
            invalidField.focus();
            return false;
        }
        return true;
    }

    function validateSharedSecret() {
        const element = sharedSecretField();
        if (!element) {
            return true;
        }
        const valid = Boolean(String(element.value || "").trim());
        element.classList.toggle("is-invalid", !valid);
        element.setCustomValidity(valid ? "" : "Shared secret is required.");
        if (!valid) {
            element.reportValidity();
            element.focus();
        }
        return valid;
    }

    function vtiNumber(name) {
        const match = String(name || "").match(/^vti(\d+)$/i);
        return match ? Number(match[1]) : 0;
    }

    function markNumber(value) {
        const match = String(value || "").trim().match(/^(\d+)(?:\/0x[0-9a-fA-F]+)?$/);
        return match ? Number(match[1]) : 0;
    }

    function nextVtiInterface() {
        const usedNumbers = interfaceInventory
            .filter((iface) => /^vti/i.test(String(iface.name || "")))
            .map((iface) => vtiNumber(iface.name))
            .concat(latestConnections.map((connection) => vtiNumber(connection.vti_interface)))
            .filter((number) => number > 0);
        const used = new Set(usedNumbers);
        let next = 1;
        while (used.has(next)) {
            next += 1;
        }
        return `vti${next}`;
    }

    function nextMark() {
        const used = new Set(
            latestConnections
                .map((connection) => markNumber(connection.mark))
                .filter((number) => number > 0)
        );
        let next = 5;
        while (used.has(next)) {
            next += 1;
        }
        return `${next}/0xffffffff`;
    }

    function setNextVtiInterface() {
        if (!field("libreswan-id").value) {
            field("libreswan-vti-interface").value = nextVtiInterface();
        }
    }

    function setNextMark() {
        if (!field("libreswan-id").value) {
            field("libreswan-mark").value = nextMark();
        }
    }

    async function loadInterfaceInventory() {
        try {
            const data = await HF.fetchJson("/api/interfaces");
            interfaceInventory = data.interfaces || [];
        } catch (_error) {
            interfaceInventory = [];
        }
        setNextVtiInterface();
    }

    function formPayload() {
        return {
            conn_name: field("libreswan-conn-name").value,
            description: field("libreswan-description").value,
            enabled: Number(field("libreswan-enabled").value),
            left_addr: field("libreswan-left-addr").value,
            left_id: field("libreswan-left-id").value,
            right_addr: field("libreswan-right-addr").value,
            shared_secret: field("libreswan-shared-secret").value,
            leftsubnet: field("libreswan-leftsubnet").value,
            rightsubnet: field("libreswan-rightsubnet").value,
            auto: field("libreswan-auto").value,
            mark: field("libreswan-mark").value,
            vti_interface: field("libreswan-vti-interface").value,
            vti_addr: field("libreswan-vti-addr").value,
            vti_mtu: field("libreswan-vti-mtu").value,
            vti_routing: field("libreswan-vti-routing").value,
            ikev2: field("libreswan-ikev2").value,
            ike: field("libreswan-ike").value,
            phase2alg: field("libreswan-phase2alg").value,
            encapsulation: field("libreswan-encapsulation").value,
            ikelifetime: field("libreswan-ikelifetime").value,
            salifetime: field("libreswan-salifetime").value,
        };
    }

    function setFormStatus(message, failed = false) {
        if (!formStatus) {
            return;
        }
        formStatus.hidden = false;
        formStatus.textContent = message;
        formStatus.classList.toggle("error", failed);
    }

    function clearForm() {
        field("libreswan-id").value = "";
        field("libreswan-conn-name").value = "";
        field("libreswan-description").value = "";
        field("libreswan-enabled").value = "1";
        field("libreswan-left-addr").value = "";
        field("libreswan-left-id").value = "";
        field("libreswan-right-addr").value = "";
        field("libreswan-shared-secret").value = "";
        setSharedSecretVisible(false);
        field("libreswan-leftsubnet").value = "0.0.0.0/0";
        field("libreswan-rightsubnet").value = "0.0.0.0/0";
        field("libreswan-auto").value = "start";
        setNextMark();
        setNextVtiInterface();
        field("libreswan-vti-addr").value = "";
        field("libreswan-vti-mtu").value = "";
        field("libreswan-vti-routing").value = "no";
        field("libreswan-ikev2").value = "no";
        field("libreswan-ike").value = "aes_cbc256-sha2_384;modp1536";
        field("libreswan-phase2alg").value = "aes_gcm256;modp1536";
        field("libreswan-encapsulation").value = "yes";
        field("libreswan-ikelifetime").value = "28800s";
        field("libreswan-salifetime").value = "3600s";
        if (formTitle) {
            formTitle.textContent = "New IPsec Connection";
        }
        if (formState) {
            formState.textContent = "mode=create";
        }
        if (submitButton) {
            submitButton.textContent = "Add connection";
        }
        if (formStatus) {
            formStatus.hidden = true;
            formStatus.textContent = "";
            formStatus.classList.remove("error");
        }
    }

    function editConnection(connectionId) {
        const item = latestConnections.find((connection) => Number(connection.id) === Number(connectionId));
        if (!item) {
            return;
        }
        field("libreswan-id").value = item.id;
        field("libreswan-conn-name").value = item.conn_name || "";
        field("libreswan-description").value = item.description || "";
        field("libreswan-enabled").value = String(item.enabled ?? 1);
        field("libreswan-left-addr").value = item.left_addr || "";
        field("libreswan-left-id").value = item.left_id || "";
        field("libreswan-right-addr").value = item.right_addr || "";
        field("libreswan-shared-secret").value = item.shared_secret || "";
        setSharedSecretVisible(false);
        field("libreswan-leftsubnet").value = item.leftsubnet || "0.0.0.0/0";
        field("libreswan-rightsubnet").value = item.rightsubnet || "0.0.0.0/0";
        field("libreswan-auto").value = item.auto || "start";
        field("libreswan-mark").value = item.mark || "";
        field("libreswan-vti-interface").value = item.vti_interface || "";
        field("libreswan-vti-addr").value = item.vti_addr || "";
        field("libreswan-vti-mtu").value = Number(item.vti_mtu || 0) > 0 ? String(item.vti_mtu) : "";
        field("libreswan-vti-routing").value = item.vti_routing || "no";
        field("libreswan-ikev2").value = item.ikev2 || "no";
        setSelectValue("libreswan-ike", item.ike || "aes_cbc256-sha2_384;modp1536");
        setSelectValue("libreswan-phase2alg", item.phase2alg || "aes_gcm256;modp1536");
        field("libreswan-encapsulation").value = item.encapsulation || "yes";
        field("libreswan-ikelifetime").value = item.ikelifetime || "28800s";
        field("libreswan-salifetime").value = item.salifetime || "3600s";
        if (formTitle) {
            formTitle.textContent = "Edit IPsec Connection";
        }
        if (formState) {
            formState.textContent = `mode=edit id=${item.id}`;
        }
        if (submitButton) {
            submitButton.textContent = "Save connection";
        }
        setActiveView("new-connection");
        formPanel?.scrollIntoView({behavior: "smooth", block: "start"});
    }

    function renderConnections(connections) {
        if (connectionsCount) {
            connectionsCount.textContent = `connections=${connections.length}`;
        }
        if (!connectionsBody) {
            return;
        }
        if (!connections.length) {
            connectionsBody.innerHTML = `
                <tr>
                    <td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>no Libreswan connections configured</span></div></td>
                </tr>
            `;
            return;
        }
        connectionsBody.innerHTML = connections.map((item) => `
            <tr>
                <td>
                    <div class="libreswan-connection-name">
                        <strong>${HF.escapeHtml(item.conn_name)}</strong>
                        <span class="status ${ipsecStatusClass(item.ipsec_status)}">${ipsecStatusLabel(item.ipsec_status)}</span>
                    </div>
                    <span class="muted">${Number(item.enabled) === 1 ? "enabled" : "disabled"}${item.description ? ` / ${HF.escapeHtml(item.description)}` : ""}</span>
                </td>
                <td>
                    <strong>${HF.escapeHtml(item.left_addr)}</strong>
                    <span class="muted"> -> </span>
                    <strong>${HF.escapeHtml(item.right_addr)}</strong>
                </td>
                <td>${HF.escapeHtml(item.leftsubnet)} -> ${HF.escapeHtml(item.rightsubnet)}</td>
                <td>${HF.escapeHtml(item.vti_interface)}${item.vti_addr ? `<br><span class="muted">${HF.escapeHtml(item.vti_addr)}</span>` : ""}${Number(item.vti_mtu || 0) > 0 ? `<br><span class="muted">mtu=${HF.escapeHtml(item.vti_mtu)}</span>` : ""}<br><span class="muted">mark=${HF.escapeHtml(item.mark)}</span></td>
                <td>${HF.escapeHtml(item.ikev2)}<br><span class="muted">${HF.escapeHtml(item.ike)}</span></td>
                <td class="table-actions">
                    <button class="text-button compact" type="button" data-libreswan-edit="${HF.escapeHtml(item.id)}">Edit</button>
                    <button class="text-button compact" type="button" data-libreswan-toggle="${HF.escapeHtml(item.id)}">${Number(item.enabled) === 1 ? "Disable" : "Enable"}</button>
                    <button class="text-button compact danger" type="button" data-libreswan-delete="${HF.escapeHtml(item.id)}">Delete</button>
                </td>
            </tr>
        `).join("");
    }

    function renderConfig(data) {
        const summary = data.summary || {};
        latestConnections = data.connections || [];
        setMetric("#libreswan-summary-connections", summary.connections);
        setMetric("#libreswan-summary-enabled", summary.enabled);
        setMetric("#libreswan-summary-disabled", summary.disabled);
        renderConnections(latestConnections);
        setNextVtiInterface();
        setNextMark();
        setState("Live", summary.updated_at || "-");
    }

    async function loadConfig() {
        if (loading) {
            return;
        }
        loading = true;
        try {
            setState("Polling");
            renderConfig(await HF.fetchJson("/api/services/libreswan"));
            if (logsPanel && !logsPanel.hidden) {
                await loadLogs();
            }
            if (workRequestsPanel && !workRequestsPanel.hidden) {
                await loadWorkRequests();
            }
        } catch (error) {
            setState("Offline");
            if (connectionsBody) {
                connectionsBody.innerHTML = `
                    <tr>
                        <td colspan="7"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                    </tr>
                `;
            }
        } finally {
            loading = false;
        }
    }

    function renderLogs(data) {
        const summary = data.summary || {};
        const lines = data.lines || [];
        if (logsCount) {
            logsCount.textContent = `lines=${HF.text(summary.rows || 0)}`;
        }
        if (logsOutput) {
            const shouldFollow = logsOutput.scrollHeight - logsOutput.scrollTop - logsOutput.clientHeight < 24;
            logsOutput.textContent = lines.length ? lines.join("\n") : "Libreswan stdout/stderr logs are empty.";
            if (shouldFollow) {
                logsOutput.scrollTop = logsOutput.scrollHeight;
            }
        }
    }

    async function loadLogs() {
        if (logsLoading || !logsPanel || logsPanel.hidden) {
            return;
        }
        logsLoading = true;
        try {
            renderLogs(await HF.fetchJson("/api/services/libreswan/logs"));
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
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no Libreswan work requests</span></div></td>
                </tr>
            `;
            return;
        }
        workRequestsBody.innerHTML = requests.map((request) => `
            <tr>
                <td>${HF.escapeHtml(request.id)}</td>
                <td><span class="status ${workRequestStatusClass(request.status)}">${HF.escapeHtml(request.status)}</span></td>
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
            renderWorkRequests(await HF.fetchJson("/api/services/libreswan/work-requests"));
        } finally {
            workRequestsLoading = false;
        }
    }

    async function resolveServiceAction(action) {
        if (action !== "start-restart") {
            return action;
        }
        try {
            const data = await HF.fetchJson("/api/services/status");
            const services = []
                .concat(Array.isArray(data.services) ? data.services : [])
                .concat(Array.isArray(data.optional_services) ? data.optional_services : []);
            const libreswan = services.find((service) => String(service.name || "") === "libreswan");
            return String(libreswan?.state || "").toUpperCase() === "RUNNING" ? "restart" : "start";
        } catch (_error) {
            return "start";
        }
    }

    async function runServiceAction(action) {
        const resolvedAction = await resolveServiceAction(action);
        await HF.fetchJson("/api/services/status/libreswan/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({action: resolvedAction}),
        });
        setActiveView("work-requests");
        await loadWorkRequests();
        await loadConfig();
        document.querySelector("#main-content")?.scrollTo({top: 0, behavior: "smooth"});
        window.scrollTo({top: 0, behavior: "smooth"});
    }

    async function saveConnection(event) {
        event.preventDefault();
        if (!validateIpv4Fields()) {
            return;
        }
        if (!validateIpv4CidrFields()) {
            return;
        }
        if (!validateSharedSecret()) {
            return;
        }
        const connectionId = field("libreswan-id").value;
        const isEdit = Boolean(connectionId);
        try {
            await HF.fetchJson(isEdit ? `/api/services/libreswan/connections/${connectionId}` : "/api/services/libreswan/connections", {
                method: isEdit ? "PUT" : "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(formPayload()),
            });
            setFormStatus(isEdit ? "Connection updated." : "Connection created.");
            clearForm();
            setActiveView("connections");
            await loadConfig();
        } catch (error) {
            setFormStatus(error.message, true);
        }
    }

    async function toggleConnection(connectionId) {
        const item = latestConnections.find((connection) => Number(connection.id) === Number(connectionId));
        if (!item) {
            return;
        }
        await HF.fetchJson(`/api/services/libreswan/connections/${connectionId}/enabled`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({enabled: Number(item.enabled) !== 1}),
        });
        await loadConfig();
    }

    async function deleteConnection(connectionId) {
        await HF.fetchJson(`/api/services/libreswan/connections/${connectionId}`, {method: "DELETE"});
        await loadConfig();
        await loadWorkRequests();
        setActiveView("work-requests");
    }

    viewButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (button.dataset.libreswanView === "new-connection") {
                clearForm();
            }
            setActiveView(button.dataset.libreswanView);
        });
    });

    serviceActionButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            try {
                await runServiceAction(button.dataset.libreswanServiceAction);
            } catch (error) {
                setState(error.message);
            }
        });
    });

    connectionsBody?.addEventListener("click", async (event) => {
        const editButton = event.target.closest("[data-libreswan-edit]");
        const toggleButton = event.target.closest("[data-libreswan-toggle]");
        const deleteButton = event.target.closest("[data-libreswan-delete]");
        try {
            if (editButton) {
                editConnection(editButton.dataset.libreswanEdit);
            } else if (toggleButton) {
                await toggleConnection(toggleButton.dataset.libreswanToggle);
            } else if (deleteButton) {
                await deleteConnection(deleteButton.dataset.libreswanDelete);
            }
        } catch (error) {
            setState(error.message);
        }
    });

    form?.addEventListener("submit", saveConnection);
    clearButton?.addEventListener("click", clearForm);
    secretGenerateButton?.addEventListener("click", generateSharedSecret);
    secretToggleButton?.addEventListener("click", () => {
        const element = sharedSecretField();
        setSharedSecretVisible(element?.type !== "text");
    });
    document.querySelectorAll("[data-ipv4-address]").forEach((element) => {
        element.addEventListener("input", () => normalizeIpv4Field(element));
        element.addEventListener("blur", () => setIpv4Validity(element));
    });
    document.querySelectorAll("[data-ipv4-cidr]").forEach((element) => {
        element.addEventListener("input", () => normalizeIpv4CidrField(element));
        element.addEventListener("blur", () => setIpv4CidrValidity(element));
    });

    loadInterfaceInventory();
    clearForm();
    loadConfig();
    window.setInterval(loadConfig, POLL_MS);
    window.setInterval(loadLogs, LOG_POLL_MS);
})();
