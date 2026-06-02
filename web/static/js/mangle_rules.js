(function () {
    const stateLabel = document.querySelector("#mangle-rules-state");
    const formStatus = document.querySelector("#mangle-form-status");
    const workRequestsBody = document.querySelector("#mangle-work-requests-body");
    const workRequestsCount = document.querySelector("#mangle-work-requests-count");
    const applyModal = document.querySelector("#mangle-apply-modal");
    const applyChainLabel = document.querySelector("#mangle-apply-chain");
    const applyMessage = document.querySelector("#mangle-apply-message");
    const applyConfirmButton = document.querySelector("[data-apply-confirm]");
    const deleteModal = document.querySelector("#mangle-delete-modal");
    const deleteRuleLabel = document.querySelector("#mangle-delete-rule");
    const deleteMessage = document.querySelector("#mangle-delete-message");
    const deleteConfirmButton = document.querySelector("[data-delete-confirm]");
    const ruleForm = document.querySelector("#mangle-rule-form");
    const familySelect = document.querySelector("#mangle-family");
    const chainSelect = document.querySelector("#mangle-chain");
    const protocolSelect = document.querySelector("#mangle-protocol");
    const ifaceInSelect = document.querySelector("#mangle-iface-in");
    const ifaceOutSelect = document.querySelector("#mangle-iface-out");
    const srcAddr = document.querySelector("#mangle-src-addr");
    const dstAddr = document.querySelector("#mangle-dst-addr");
    const submitButton = document.querySelector("#mangle-submit-button");
    const createButtons = Array.from(document.querySelectorAll("[data-mangle-create-for]"));
    const chainButtons = Array.from(document.querySelectorAll("[data-mangle-chain-tab]"));
    const chainPanels = Array.from(document.querySelectorAll("[data-mangle-chain-panel]"));
    const chainApplyPanels = Array.from(document.querySelectorAll("[data-mangle-chain-apply-panel]"));
    const applyChainButtons = Array.from(document.querySelectorAll("[data-mangle-chain-apply]"));
    const MANGLE_CHAINS = ["PREROUTING", "INPUT", "FORWARD", "OUTPUT", "POSTROUTING"];
    let pendingApplyRequest = null;
    let pendingDeleteButton = null;
    let currentRulesByKey = new Map();
    let currentChains = {};
    let workRequestsPoller = null;
    let workRequestsLoading = false;
    let activeChain = "PREROUTING";
    let activeTab = "rules";
    const chainPagination = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, {page: 1, pageSize: 25}]));
    const WORK_REQUESTS_POLL_MS = 3000;
    const rulesBodies = {
        PREROUTING: document.querySelector("#mangle-prerouting-body"),
        INPUT: document.querySelector("#mangle-input-body"),
        FORWARD: document.querySelector("#mangle-forward-body"),
        OUTPUT: document.querySelector("#mangle-output-body"),
        POSTROUTING: document.querySelector("#mangle-postrouting-body"),
    };
    const ruleCounts = {
        PREROUTING: document.querySelector("#mangle-prerouting-count"),
        INPUT: document.querySelector("#mangle-input-count"),
        FORWARD: document.querySelector("#mangle-forward-count"),
        OUTPUT: document.querySelector("#mangle-output-count"),
        POSTROUTING: document.querySelector("#mangle-postrouting-count"),
    };
    const familyFilterSelects = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-family-filter='${chain}']`)]));
    const originFilterSelects = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-origin-filter='${chain}']`)]));
    const pageStatusLabels = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-page-status='${chain}']`)]));
    const pagePrevButtons = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-page-prev='${chain}']`)]));
    const pageNextButtons = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-page-next='${chain}']`)]));
    const pageSizeSelects = Object.fromEntries(MANGLE_CHAINS.map((chain) => [chain, document.querySelector(`[data-mangle-page-size='${chain}']`)]));

    function setState(value) {
        if (stateLabel) {
            stateLabel.textContent = value;
        }
    }

    function setFormStatus(value) {
        if (formStatus) {
            formStatus.textContent = value;
        }
    }

    function setActiveChain(chain) {
        activeChain = chain || "PREROUTING";
        chainButtons.forEach((button) => {
            button.classList.toggle("active", activeTab === "rules" && button.dataset.mangleChainTab === activeChain);
        });
        chainPanels.forEach((panel) => {
            panel.hidden = panel.dataset.mangleChainPanel !== activeChain;
        });
        chainApplyPanels.forEach((panel) => {
            panel.hidden = activeTab !== "rules" || panel.dataset.mangleChainApplyPanel !== activeChain;
        });
    }

    function createContextForTab(tabName) {
        return tabName === "new-rule" ? "rules" : tabName;
    }

    function setActiveTab(tabName, refreshData = false) {
        const createContext = createContextForTab(tabName);
        activeTab = createContext === "rules" ? "rules" : tabName;
        document.querySelectorAll("[data-mangle-tab]").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.mangleTab === tabName);
        });
        document.querySelectorAll("[data-mangle-view]").forEach((view) => {
            view.hidden = view.dataset.mangleView !== tabName;
        });
        createButtons.forEach((button) => {
            button.hidden = button.dataset.mangleCreateFor !== createContext;
        });
        setActiveChain(activeChain);
        if (tabName !== "work-requests") {
            stopWorkRequestsPolling();
        }
        if (!refreshData) {
            return;
        }
        if (tabName === "rules") {
            loadRules();
        } else if (tabName === "new-rule") {
            loadInterfaceChoices();
            setSelectValue(chainSelect, activeChain);
            updateFormShape();
        } else if (tabName === "work-requests") {
            startWorkRequestsPolling();
        }
    }

    function startWorkRequestsPolling() {
        loadWorkRequests();
        if (!workRequestsPoller) {
            workRequestsPoller = window.setInterval(loadWorkRequests, WORK_REQUESTS_POLL_MS);
        }
    }

    function stopWorkRequestsPolling() {
        if (workRequestsPoller) {
            window.clearInterval(workRequestsPoller);
            workRequestsPoller = null;
        }
    }

    function replaceOptions(select, options) {
        if (!select) {
            return;
        }
        select.innerHTML = "";
        options.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.value;
            option.textContent = item.label;
            select.appendChild(option);
        });
    }

    function setSelectValue(select, value) {
        if (!select) {
            return;
        }
        const nextValue = value === null || value === undefined ? "" : String(value);
        if (nextValue && !Array.from(select.options).some((option) => option.value === nextValue)) {
            const option = document.createElement("option");
            option.value = nextValue;
            option.textContent = nextValue;
            select.appendChild(option);
        }
        select.value = nextValue;
    }

    function setFieldHidden(field, shouldHide) {
        field.hidden = shouldHide;
        field.classList.toggle("is-hidden", shouldHide);
        field.querySelectorAll("select, input").forEach((element) => {
            element.disabled = shouldHide;
        });
    }

    function updateMetric(id, value) {
        const element = document.querySelector(id);
        if (element) {
            element.textContent = HF.number(value).toLocaleString();
        }
    }

    function ruleKey(family, chain, ruleId) {
        return `${family}:${chain}:${ruleId}`;
    }

    function portLabel(port) {
        return port === null || port === undefined || port === "" || Number(port) === 0 ? "*" : String(port);
    }

    function interfaceOptionLabel(iface) {
        const role = iface.role || "UNKNOWN";
        const state = HF.number(iface.is_actived) === 1 ? "UP" : "DOWN";
        const mac = iface.mac_address || "no-mac";
        return `${iface.name} (${role}, ${state}, ${mac})`;
    }

    function renderInterfaceChoices(interfaces) {
        const options = [{value: "ANY", label: "any"}].concat(
            interfaces.map((iface) => ({
                value: iface.name,
                label: interfaceOptionLabel(iface),
            })),
        );
        replaceOptions(ifaceInSelect, options);
        replaceOptions(ifaceOutSelect, options);
    }

    async function loadInterfaceChoices() {
        try {
            const data = await HF.fetchJson("/api/interfaces");
            renderInterfaceChoices(data.interfaces || []);
        } catch (error) {
            const options = [{value: "", label: `interfaces unavailable: ${error.message}`}];
            replaceOptions(ifaceInSelect, options);
            replaceOptions(ifaceOutSelect, options);
        }
    }

    function updateFormShape() {
        const family = familySelect ? familySelect.value : "IPV4";
        const chain = chainSelect ? chainSelect.value : "PREROUTING";
        const protocol = protocolSelect ? protocolSelect.value : "tcp";
        const isIcmp = protocol === "icmp";
        const isAny = protocol === "all";
        const isEsp = protocol === "esp";
        const wildcard = family === "IPV6" ? "::/0" : "0.0.0.0/0";

        if (srcAddr && (srcAddr.value === "" || srcAddr.value === "0.0.0.0/0" || srcAddr.value === "::/0")) {
            srcAddr.value = wildcard;
        }
        if (dstAddr && (dstAddr.value === "" || dstAddr.value === "0.0.0.0/0" || dstAddr.value === "::/0")) {
            dstAddr.value = wildcard;
        }
        document.querySelectorAll("[data-iface-in-field]").forEach((field) => setFieldHidden(field, chain === "OUTPUT" || chain === "POSTROUTING"));
        document.querySelectorAll("[data-iface-out-field]").forEach((field) => setFieldHidden(field, chain === "PREROUTING" || chain === "INPUT"));
        document.querySelectorAll("[data-port-field]").forEach((field) => setFieldHidden(field, isIcmp || isAny || isEsp));
    }

    function payloadFromForm() {
        const formData = new FormData(ruleForm);
        const conntrackMode = String(formData.get("conntrack_mode") || "");
        const payload = Object.fromEntries(formData.entries());
        payload.ct_new = conntrackMode === "new" ? 1 : 0;
        payload.ct_established = conntrackMode === "established-related" ? 1 : 0;
        payload.ct_related = conntrackMode === "established-related" ? 1 : 0;
        payload.ct_invalid = 0;
        delete payload.conntrack_mode;
        return payload;
    }

    function conntrackLabel(rule) {
        const states = [];
        if (HF.number(rule.ct_new) === 1) states.push("NEW");
        if (HF.number(rule.ct_established) === 1) states.push("EST");
        if (HF.number(rule.ct_related) === 1) states.push("REL");
        if (HF.number(rule.ct_invalid) === 1) states.push("INV");
        return states.length ? states.join(",") : "-";
    }

    function interfaceLabel(rule) {
        if (rule.chain === "OUTPUT" || rule.chain === "POSTROUTING") {
            return `out=${HF.escapeHtml(rule.iface_out || "*")}`;
        }
        if (rule.chain === "FORWARD") {
            return `in=${HF.escapeHtml(rule.iface_in || "*")}<br>out=${HF.escapeHtml(rule.iface_out || "*")}`;
        }
        return `in=${HF.escapeHtml(rule.iface_in || "*")}`;
    }

    function endpointLabel(rule, prefix) {
        const addr = rule[`${prefix}_addr`];
        const port = rule[`${prefix}_port`];
        return `${HF.escapeHtml(addr)}<br><span class="muted">port=${HF.escapeHtml(portLabel(port))}</span>`;
    }

    function valuesLabel(rule) {
        const values = [];
        if (rule.mark_value) values.push(`mark=${rule.mark_value}`);
        if (rule.dscp_value) values.push(`dscp=${rule.dscp_value}`);
        if (rule.tos_value) values.push(`tos=${rule.tos_value}`);
        if (rule.ttl_value) values.push(`ttl=${rule.ttl_value}`);
        return values.length ? HF.escapeHtml(values.join(" ")) : "-";
    }

    function ruleRow(rule) {
        const enabled = HF.number(rule.enabled) === 1;
        const applied = HF.number(rule.applied) === 1;
        const pendingDelete = HF.number(rule.pending_delete) === 1;
        const protectedRule = HF.number(rule.protected) === 1;
        const statusClass = pendingDelete ? "down" : !enabled ? "disabled" : applied ? "up" : "down";
        const statusLabel = pendingDelete ? "PENDING DELETE" : !enabled ? "DISABLED" : applied ? "ACTIVE" : "PENDING APPLY";
        const protectedBadge = protectedRule ? '<span class="status protected">PROTECTED</span>' : "";
        const nextEnabled = enabled ? 0 : 1;
        const buttonLabel = enabled ? "Disable" : "Enable";
        const toggleDisabled = pendingDelete || (enabled && protectedRule) ? "disabled" : "";
        const deleteDisabled = pendingDelete || protectedRule || !enabled ? "disabled" : "";
        const toggleTitle = pendingDelete ? "Rules pending deletion cannot be changed" : !enabled ? "Enable rule" : protectedRule ? "Protected rules cannot be disabled" : "Disable rule";
        const deleteTitle = pendingDelete ? "Rule is pending deletion" : !enabled ? "Disabled rules cannot be deleted" : protectedRule ? "Protected rules cannot be deleted" : "Delete rule";

        return `
            <tr>
                <td><span class="role">${HF.escapeHtml(rule.family)}</span></td>
                <td>${HF.escapeHtml(rule.rule_order)}</td>
                <td><strong>${HF.escapeHtml(rule.mangle_action)}</strong></td>
                <td>${interfaceLabel(rule)}</td>
                <td>${HF.escapeHtml(rule.protocol_name)}</td>
                <td>${endpointLabel(rule, "src")}</td>
                <td>${endpointLabel(rule, "dst")}</td>
                <td>${HF.escapeHtml(conntrackLabel(rule))}</td>
                <td>${valuesLabel(rule)}</td>
                <td>
                    <span class="status ${statusClass}">${statusLabel}</span>
                    ${protectedBadge}
                </td>
                <td>
                    <button class="text-button compact" type="button"
                        data-rule-toggle
                        data-family="${HF.escapeHtml(rule.family)}"
                        data-chain="${HF.escapeHtml(rule.chain)}"
                        data-rule-id="${HF.escapeHtml(rule.id)}"
                        data-enabled="${nextEnabled}"
                        title="${toggleTitle}"
                        ${toggleDisabled}>
                        ${buttonLabel}
                    </button>
                    <button class="text-button compact danger" type="button"
                        data-rule-delete
                        data-family="${HF.escapeHtml(rule.family)}"
                        data-chain="${HF.escapeHtml(rule.chain)}"
                        data-rule-id="${HF.escapeHtml(rule.id)}"
                        title="${deleteTitle}"
                        ${deleteDisabled}>
                        Delete
                    </button>
                </td>
            </tr>
        `;
    }

    function familyLabel(family) {
        return family === "IPV4" ? "IPv4" : "IPv6";
    }

    function compareRulesForDisplay(left, right) {
        const leftPending = String(left.apply_state || "") === "pending" ? 0 : 1;
        const rightPending = String(right.apply_state || "") === "pending" ? 0 : 1;
        if (leftPending !== rightPending) {
            return leftPending - rightPending;
        }

        const leftOrder = HF.number(left.rule_order);
        const rightOrder = HF.number(right.rule_order);
        if (leftOrder !== rightOrder) {
            return leftOrder - rightOrder;
        }

        return HF.number(left.id) - HF.number(right.id);
    }

    function renderChain(chain, rules) {
        const body = rulesBodies[chain];
        const count = ruleCounts[chain];
        const chainRules = rules || [];
        const activeFamily = familyFilterSelects[chain] ? familyFilterSelects[chain].value : "IPV4";
        const activeOrigin = originFilterSelects[chain] ? originFilterSelects[chain].value : "all";
        const filteredRules = chainRules
            .filter((rule) => rule.family === activeFamily)
            .filter((rule) => activeOrigin !== "user" || HF.number(rule.user_defined) === 1)
            .slice()
            .sort(compareRulesForDisplay);
        const pagination = chainPagination[chain] || {page: 1, pageSize: 25};
        const totalItems = filteredRules.length;
        const totalPages = Math.max(1, Math.ceil(totalItems / pagination.pageSize));
        pagination.page = Math.min(Math.max(1, pagination.page), totalPages);
        const startIndex = totalItems ? (pagination.page - 1) * pagination.pageSize : 0;
        const endIndex = Math.min(startIndex + pagination.pageSize, totalItems);
        const visibleRules = filteredRules.slice(startIndex, endIndex);

        if (count) {
            const originLabel = activeOrigin === "user" ? " user-defined" : "";
            count.textContent = `${familyLabel(activeFamily)}${originLabel} rules=${filteredRules.length}`;
        }
        updatePagination(chain, pagination.page, totalPages, totalItems, startIndex, endIndex);
        if (!body) {
            return;
        }
        if (!visibleRules.length) {
            body.innerHTML = `
                <tr>
                    <td colspan="11">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no ${familyLabel(activeFamily)}${activeOrigin === "user" ? " user defined" : ""} ${HF.escapeHtml(chain)} mangle rules</span></div>
                    </td>
                </tr>
            `;
            return;
        }
        body.innerHTML = visibleRules.map(ruleRow).join("");
    }

    function updatePagination(chain, page, totalPages, totalItems, startIndex, endIndex) {
        const status = pageStatusLabels[chain];
        const prev = pagePrevButtons[chain];
        const next = pageNextButtons[chain];
        const firstItem = totalItems ? startIndex + 1 : 0;
        const lastItem = totalItems ? endIndex : 0;
        if (status) {
            status.textContent = `Page ${page} of ${totalPages} (${firstItem} - ${lastItem} of ${totalItems} total items)`;
        }
        if (prev) {
            prev.disabled = page <= 1;
        }
        if (next) {
            next.disabled = page >= totalPages;
        }
    }

    function renderRules(data) {
        const chains = data.chains || {};
        currentChains = chains;
        currentRulesByKey = new Map();
        (data.rules || []).forEach((rule) => {
            currentRulesByKey.set(ruleKey(rule.family, rule.chain, rule.id), rule);
        });
        updateMetric("#mangle-summary-total", data.summary.total);
        updateMetric("#mangle-summary-enabled", data.summary.enabled);
        updateMetric("#mangle-summary-disabled", data.summary.disabled);
        updateMetric("#mangle-summary-protected", data.summary.protected);
        MANGLE_CHAINS.forEach((chain) => renderChain(chain, chains[chain] || []));
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
                    <td colspan="7">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no mangle work requests</span></div>
                    </td>
                </tr>
            `;
            return;
        }
        workRequestsBody.innerHTML = requests.map((request) => {
            const failed = request.status === "failed";
            const statusClass = failed ? "down" : "up";
            return `
                <tr>
                    <td>${HF.escapeHtml(request.id)}</td>
                    <td><span class="status ${statusClass}">${HF.escapeHtml(request.status)}</span></td>
                    <td>${HF.escapeHtml(request.category_name)}</td>
                    <td>${HF.escapeHtml(request.action_name)}</td>
                    <td>${HF.escapeHtml(request.target_rule_id)}</td>
                    <td>${HF.escapeHtml(request.updated_at)}</td>
                    <td>${HF.escapeHtml(request.error_message)}</td>
                </tr>
            `;
        }).join("");
    }

    function openApplyModal(chain, family) {
        pendingApplyRequest = {chain, family};
        const chainRules = Array.from(currentRulesByKey.values()).filter((rule) => rule.chain === chain && rule.family === family);
        const pendingCount = chainRules.filter((rule) => String(rule.apply_state || "") === "pending").length;

        if (applyChainLabel) {
            applyChainLabel.textContent = `chain=${chain} family=${family}`;
        }
        if (applyMessage) {
            applyMessage.textContent = `Are you sure you want to apply ${pendingCount} pending rule(s) from the ${chain} chain for ${familyLabel(family)}?`;
        }
        if (applyModal) {
            applyModal.hidden = false;
        }
    }

    function closeApplyModal() {
        pendingApplyRequest = null;
        if (applyModal) {
            applyModal.hidden = true;
        }
    }

    function openDeleteModal(button) {
        pendingDeleteButton = button;
        const family = button.dataset.family;
        const chain = button.dataset.chain;
        const ruleId = button.dataset.ruleId;
        const rule = currentRulesByKey.get(ruleKey(family, chain, ruleId));
        const label = rule ? `${rule.family}/${rule.chain}/${rule.id}` : `${family}/${chain}/${ruleId}`;

        if (deleteRuleLabel) {
            deleteRuleLabel.textContent = `rule=${label}`;
        }
        if (deleteMessage) {
            deleteMessage.textContent = `Are you sure you want to delete rule ${label}?`;
        }
        if (deleteModal) {
            deleteModal.hidden = false;
        }
    }

    function closeDeleteModal() {
        pendingDeleteButton = null;
        if (deleteModal) {
            deleteModal.hidden = true;
        }
    }

    async function loadRules() {
        try {
            setState("Loading");
            const data = await HF.fetchJson("/api/firewall/mangle-rules");
            renderRules(data);
            setState("Ready");
        } catch (error) {
            setState("Offline");
            Object.entries(rulesBodies).forEach(([chain, body]) => {
                if (body) {
                    body.innerHTML = `
                        <tr>
                            <td colspan="11">
                                <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(chain)}: ${HF.escapeHtml(error.message)}</span></div>
                            </td>
                        </tr>
                    `;
                }
            });
        }
    }

    async function loadWorkRequests() {
        if (workRequestsLoading) {
            return;
        }
        workRequestsLoading = true;
        try {
            const data = await HF.fetchJson("/api/firewall/mangle-rules/work-requests");
            renderWorkRequests(data);
        } catch (error) {
            if (workRequestsBody) {
                workRequestsBody.innerHTML = `
                    <tr>
                        <td colspan="7">
                            <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
                        </td>
                    </tr>
                    `;
            }
        } finally {
            workRequestsLoading = false;
        }
    }

    async function applyChain() {
        if (!pendingApplyRequest) {
            return;
        }
        try {
            if (applyConfirmButton) {
                applyConfirmButton.disabled = true;
            }
            setFormStatus("queue=writing");
            const {chain, family} = pendingApplyRequest;
            const result = await HF.fetchJson(`/api/firewall/mangle-rules/${chain}/apply`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({family}),
            });
            setFormStatus(`queued=${result.work_request_count}`);
            closeApplyModal();
            setActiveTab("work-requests", true);
        } catch (error) {
            setFormStatus(`error=${error.message}`);
        } finally {
            if (applyConfirmButton) {
                applyConfirmButton.disabled = false;
            }
        }
    }

    async function submitRule(event) {
        event.preventDefault();
        try {
            setFormStatus("queue=writing");
            const payload = payloadFromForm();
            const result = await HF.fetchJson("/api/firewall/mangle-rules", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            });
            setFormStatus(`saved=${result.rule_id}`);
            setActiveChain(payload.chain);
            ruleForm.reset();
            updateFormShape();
            setActiveTab("rules", true);
        } catch (error) {
            setFormStatus(`error=${error.message}`);
        }
    }

    async function toggleRule(button) {
        try {
            button.disabled = true;
            setFormStatus("queue=writing");
            const family = button.dataset.family;
            const chain = button.dataset.chain;
            const ruleId = button.dataset.ruleId;
            const enabled = Number(button.dataset.enabled);
            const result = await HF.fetchJson(`/api/firewall/mangle-rules/${family}/${chain}/${ruleId}/enabled`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({enabled}),
            });
            setFormStatus(`saved=${result.rule_id}`);
            await loadRules();
        } catch (error) {
            setFormStatus(`error=${error.message}`);
            button.disabled = false;
        }
    }

    async function deleteRule(button) {
        const family = button.dataset.family;
        const chain = button.dataset.chain;
        const ruleId = button.dataset.ruleId;

        try {
            button.disabled = true;
            if (deleteConfirmButton) {
                deleteConfirmButton.disabled = true;
            }
            setFormStatus("queue=writing");
            const result = await HF.fetchJson(`/api/firewall/mangle-rules/${family}/${chain}/${ruleId}`, {
                method: "DELETE",
            });
            setFormStatus(`saved=${result.rule_id}`);
            closeDeleteModal();
            await loadRules();
            await loadWorkRequests();
        } catch (error) {
            setFormStatus(`error=${error.message}`);
            button.disabled = false;
        } finally {
            if (deleteConfirmButton) {
                deleteConfirmButton.disabled = false;
            }
        }
    }

    document.querySelectorAll("[data-mangle-tab]").forEach((tab) => {
        tab.addEventListener("click", () => setActiveTab(tab.dataset.mangleTab, true));
    });

    chainButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setActiveChain(button.dataset.mangleChainTab);
            setActiveTab("rules", true);
        });
    });

    applyChainButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const chain = button.dataset.mangleChainApply;
            const family = familyFilterSelects[chain] ? familyFilterSelects[chain].value : "IPV4";
            openApplyModal(chain, family);
        });
    });

    Object.entries(familyFilterSelects).forEach(([chain, select]) => {
        if (select) {
            select.addEventListener("change", () => {
                chainPagination[chain].page = 1;
                renderChain(chain, currentChains[chain] || []);
            });
        }
    });

    Object.entries(originFilterSelects).forEach(([chain, select]) => {
        if (select) {
            select.addEventListener("change", () => {
                chainPagination[chain].page = 1;
                renderChain(chain, currentChains[chain] || []);
            });
        }
    });

    Object.entries(pageSizeSelects).forEach(([chain, select]) => {
        if (select) {
            select.addEventListener("change", () => {
                chainPagination[chain].page = 1;
                chainPagination[chain].pageSize = Number(select.value) || 25;
                renderChain(chain, currentChains[chain] || []);
            });
        }
    });

    Object.entries(pagePrevButtons).forEach(([chain, button]) => {
        if (button) {
            button.addEventListener("click", () => {
                chainPagination[chain].page = Math.max(1, chainPagination[chain].page - 1);
                renderChain(chain, currentChains[chain] || []);
            });
        }
    });

    Object.entries(pageNextButtons).forEach(([chain, button]) => {
        if (button) {
            button.addEventListener("click", () => {
                chainPagination[chain].page += 1;
                renderChain(chain, currentChains[chain] || []);
            });
        }
    });

    document.querySelectorAll("[data-apply-cancel]").forEach((button) => {
        button.addEventListener("click", closeApplyModal);
    });

    document.querySelectorAll("[data-delete-cancel]").forEach((button) => {
        button.addEventListener("click", closeDeleteModal);
    });

    if (applyConfirmButton) {
        applyConfirmButton.addEventListener("click", applyChain);
    }

    if (deleteConfirmButton) {
        deleteConfirmButton.addEventListener("click", () => {
            if (pendingDeleteButton) {
                deleteRule(pendingDeleteButton);
            }
        });
    }

    if (applyModal) {
        applyModal.addEventListener("click", (event) => {
            if (event.target === applyModal) {
                closeApplyModal();
            }
        });
    }

    if (deleteModal) {
        deleteModal.addEventListener("click", (event) => {
            if (event.target === deleteModal) {
                closeDeleteModal();
            }
        });
    }

    if (submitButton) {
        submitButton.textContent = "Add";
    }

    if (ruleForm) {
        ruleForm.addEventListener("submit", submitRule);
        ruleForm.addEventListener("reset", () => window.setTimeout(updateFormShape, 0));
    }

    [familySelect, chainSelect, protocolSelect].forEach((element) => {
        if (element) {
            element.addEventListener("change", updateFormShape);
        }
    });

    Object.values(rulesBodies).forEach((body) => {
        if (body) {
            body.addEventListener("click", (event) => {
                const toggleButton = event.target.closest("[data-rule-toggle]");
                const deleteButton = event.target.closest("[data-rule-delete]");

                if (toggleButton) {
                    toggleRule(toggleButton);
                    return;
                }
                if (deleteButton) {
                    openDeleteModal(deleteButton);
                }
            });
        }
    });

    updateFormShape();
    setActiveChain("PREROUTING");
    setActiveTab("rules");
    loadInterfaceChoices();
    loadRules();
}());
