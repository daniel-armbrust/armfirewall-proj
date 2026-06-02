(function () {
    const stateLabel = document.querySelector("#nat-rules-state");
    const formStatus = document.querySelector("#nat-form-status");
    const workRequestsBody = document.querySelector("#nat-work-requests-body");
    const workRequestsCount = document.querySelector("#nat-work-requests-count");
    const applyModal = document.querySelector("#nat-apply-modal");
    const applyChainLabel = document.querySelector("#nat-apply-chain");
    const applyMessage = document.querySelector("#nat-apply-message");
    const applyConfirmButton = document.querySelector("[data-apply-confirm]");
    const deleteModal = document.querySelector("#nat-delete-modal");
    const deleteRuleLabel = document.querySelector("#nat-delete-rule");
    const deleteMessage = document.querySelector("#nat-delete-message");
    const deleteConfirmButton = document.querySelector("[data-delete-confirm]");
    const ruleForm = document.querySelector("#nat-rule-form");
    const familySelect = document.querySelector("#nat-family");
    const chainSelect = document.querySelector("#nat-chain");
    const actionSelect = document.querySelector("#nat-action");
    const protocolSelect = document.querySelector("#nat-protocol");
    const ifaceInSelect = document.querySelector("#nat-iface-in");
    const ifaceOutSelect = document.querySelector("#nat-iface-out");
    const srcAddr = document.querySelector("#nat-src-addr");
    const dstAddr = document.querySelector("#nat-dst-addr");
    const submitButton = document.querySelector("#nat-submit-button");
    const createButtons = Array.from(document.querySelectorAll("[data-nat-create-for]"));
    const chainButtons = Array.from(document.querySelectorAll("[data-nat-chain-tab]"));
    const chainPanels = Array.from(document.querySelectorAll("[data-nat-chain-panel]"));
    const chainApplyPanels = Array.from(document.querySelectorAll("[data-nat-chain-apply-panel]"));
    const applyChainButtons = Array.from(document.querySelectorAll("[data-nat-chain-apply]"));
    const NAT_CHAINS = ["PREROUTING", "INPUT", "OUTPUT", "POSTROUTING"];
    let pendingApplyRequest = null;
    let pendingDeleteButton = null;
    let editingRule = null;
    let currentRulesByKey = new Map();
    let currentChains = {};
    let workRequestsPoller = null;
    let workRequestsLoading = false;
    let activeChain = "PREROUTING";
    let activeTab = "rules";
    const chainPagination = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, {page: 1, pageSize: 25}]));
    const WORK_REQUESTS_POLL_MS = 3000;
    const rulesBodies = {
        PREROUTING: document.querySelector("#nat-prerouting-body"),
        INPUT: document.querySelector("#nat-input-body"),
        OUTPUT: document.querySelector("#nat-output-body"),
        POSTROUTING: document.querySelector("#nat-postrouting-body"),
    };
    const ruleCounts = {
        PREROUTING: document.querySelector("#nat-prerouting-count"),
        INPUT: document.querySelector("#nat-input-count"),
        OUTPUT: document.querySelector("#nat-output-count"),
        POSTROUTING: document.querySelector("#nat-postrouting-count"),
    };
    const familyFilterSelects = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, document.querySelector(`[data-nat-family-filter='${chain}']`)]));
    const pageStatusLabels = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, document.querySelector(`[data-nat-page-status='${chain}']`)]));
    const pagePrevButtons = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, document.querySelector(`[data-nat-page-prev='${chain}']`)]));
    const pageNextButtons = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, document.querySelector(`[data-nat-page-next='${chain}']`)]));
    const pageSizeSelects = Object.fromEntries(NAT_CHAINS.map((chain) => [chain, document.querySelector(`[data-nat-page-size='${chain}']`)]));

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
            button.classList.toggle("active", activeTab === "rules" && button.dataset.natChainTab === activeChain);
        });
        chainPanels.forEach((panel) => {
            panel.hidden = panel.dataset.natChainPanel !== activeChain;
        });
        chainApplyPanels.forEach((panel) => {
            panel.hidden = activeTab !== "rules" || panel.dataset.natChainApplyPanel !== activeChain;
        });
    }

    function createContextForTab(tabName) {
        return tabName === "new-rule" ? "rules" : tabName;
    }

    function setActiveTab(tabName, refreshData = false) {
        const createContext = createContextForTab(tabName);
        activeTab = createContext === "rules" ? "rules" : tabName;
        document.querySelectorAll("[data-nat-tab]").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.natTab === tabName);
        });
        document.querySelectorAll("[data-nat-view]").forEach((view) => {
            view.hidden = view.dataset.natView !== tabName;
        });
        createButtons.forEach((button) => {
            button.hidden = button.dataset.natCreateFor !== createContext;
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
            if (!editingRule) {
                setSelectValue(chainSelect, activeChain);
            }
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

    function ruleKey(family, chain, ruleId) {
        return `${family}:${chain}:${ruleId}`;
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

    function updateActionChoices() {
        const chain = chainSelect ? chainSelect.value : "PREROUTING";
        const selectedAction = actionSelect ? actionSelect.value : "";
        const values = chain === "POSTROUTING" ? ["SNAT", "MASQUERADE", "ACCEPT", "RETURN"] : ["DNAT", "REDIRECT", "ACCEPT", "RETURN"];
        replaceOptions(actionSelect, values.map((value) => ({value, label: value})));
        if (selectedAction && values.includes(selectedAction)) {
            actionSelect.value = selectedAction;
        }
    }

    function updateFormShape() {
        const family = familySelect ? familySelect.value : "IPV4";
        const chain = chainSelect ? chainSelect.value : "PREROUTING";
        const protocol = protocolSelect ? protocolSelect.value : "tcp";
        const isIcmp = protocol === "icmp";
        const isAny = protocol === "all";
        const wildcard = family === "IPV6" ? "::/0" : "0.0.0.0/0";

        if (srcAddr && (srcAddr.value === "" || srcAddr.value === "0.0.0.0/0" || srcAddr.value === "::/0")) {
            srcAddr.value = wildcard;
        }
        if (dstAddr && (dstAddr.value === "" || dstAddr.value === "0.0.0.0/0" || dstAddr.value === "::/0")) {
            dstAddr.value = wildcard;
        }
        document.querySelectorAll("[data-iface-in-field]").forEach((field) => setFieldHidden(field, chain === "OUTPUT" || chain === "POSTROUTING"));
        document.querySelectorAll("[data-iface-out-field]").forEach((field) => setFieldHidden(field, chain === "PREROUTING" || chain === "INPUT"));
        document.querySelectorAll("[data-port-field]").forEach((field) => setFieldHidden(field, isIcmp || isAny));
        updateActionChoices();
    }

    function payloadFromForm() {
        return Object.fromEntries(new FormData(ruleForm).entries());
    }

    function protocolFormValue(rule) {
        if (rule.protocol_name === "icmpv6") {
            return "icmp";
        }
        return rule.protocol_name || "tcp";
    }

    function defaultAddressForFamily(family) {
        return family === "IPV6" ? "::/0" : "0.0.0.0/0";
    }

    function setFormMode(rule) {
        editingRule = rule;
        if (submitButton) {
            submitButton.textContent = rule ? "Save rule" : "Add";
        }
        setFormStatus(rule ? `editing=${rule.family}/${rule.chain}/${rule.id}` : "queue=idle");
    }

    function clearEditMode() {
        setFormMode(null);
    }

    function editRule(rule) {
        if (!rule || HF.number(rule.protected) === 1 || HF.number(rule.enabled) === 0) {
            return;
        }

        setSelectValue(familySelect, rule.family);
        setSelectValue(chainSelect, rule.chain);
        updateActionChoices();
        setSelectValue(actionSelect, rule.nat_action);
        setSelectValue(protocolSelect, protocolFormValue(rule));
        setSelectValue(ifaceInSelect, rule.iface_in);
        setSelectValue(ifaceOutSelect, rule.iface_out);
        setSelectValue(ruleForm.elements.enabled, rule.enabled);

        ruleForm.elements.src_addr.value = rule.src_addr || defaultAddressForFamily(rule.family);
        ruleForm.elements.dst_addr.value = rule.dst_addr || defaultAddressForFamily(rule.family);
        if (ruleForm.elements.src_port) {
            ruleForm.elements.src_port.value = rule.src_port === null || rule.src_port === undefined ? 0 : rule.src_port;
        }
        if (ruleForm.elements.dst_port) {
            ruleForm.elements.dst_port.value = rule.dst_port === null || rule.dst_port === undefined ? 0 : rule.dst_port;
        }
        if (ruleForm.elements.to_addr) {
            ruleForm.elements.to_addr.value = rule.to_addr || "";
        }
        if (ruleForm.elements.to_port) {
            ruleForm.elements.to_port.value = rule.to_port === null || rule.to_port === undefined ? "" : rule.to_port;
        }

        updateFormShape();
        setFormMode(rule);
        setActiveChain(rule.chain);
        setActiveTab("new-rule");
    }

    function submitUrlAndMethod() {
        if (!editingRule) {
            return {url: "/api/firewall/nat-rules", method: "POST"};
        }
        return {
            url: `/api/firewall/nat-rules/${editingRule.family}/${editingRule.chain}/${editingRule.id}`,
            method: "PUT",
        };
    }

    function interfaceLabel(rule) {
        if (rule.chain === "PREROUTING" || rule.chain === "INPUT") {
            return `in=${HF.escapeHtml(rule.iface_in || "*")}`;
        }
        return `out=${HF.escapeHtml(rule.iface_out || "*")}`;
    }

    function endpointLabel(rule, prefix) {
        const addr = rule[`${prefix}_addr`];
        const port = rule[`${prefix}_port`];
        return `${HF.escapeHtml(addr)}<br><span class="muted">port=${HF.escapeHtml(portLabel(port))}</span>`;
    }

    function translationLabel(rule) {
        const toAddr = rule.to_addr || "*";
        const toPort = portLabel(rule.to_port);
        return `${HF.escapeHtml(toAddr)}<br><span class="muted">port=${HF.escapeHtml(toPort)}</span>`;
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
        const editDisabled = pendingDelete || protectedRule || !enabled ? "disabled" : "";
        const toggleDisabled = pendingDelete || (enabled && protectedRule) ? "disabled" : "";
        const deleteDisabled = pendingDelete || protectedRule || !enabled ? "disabled" : "";
        const editTitle = pendingDelete ? "Rules pending deletion cannot be edited" : !enabled ? "Disabled rules cannot be edited" : protectedRule ? "Protected rules cannot be edited" : "Edit rule";
        const toggleTitle = pendingDelete ? "Rules pending deletion cannot be changed" : !enabled ? "Enable rule" : protectedRule ? "Protected rules cannot be disabled" : "Disable rule";
        const deleteTitle = pendingDelete ? "Rule is pending deletion" : !enabled ? "Disabled rules cannot be deleted" : protectedRule ? "Protected rules cannot be deleted" : "Delete rule";

        return `
            <tr>
                <td><span class="role">${HF.escapeHtml(rule.family)}</span></td>
                <td>${HF.escapeHtml(rule.rule_order)}</td>
                <td><strong>${HF.escapeHtml(rule.nat_action)}</strong></td>
                <td>${interfaceLabel(rule)}</td>
                <td>${HF.escapeHtml(rule.protocol_name)}</td>
                <td>${endpointLabel(rule, "src")}</td>
                <td>${endpointLabel(rule, "dst")}</td>
                <td>${translationLabel(rule)}</td>
                <td>
                    <span class="status ${statusClass}">${statusLabel}</span>
                    ${protectedBadge}
                </td>
                <td>
                    <button class="text-button compact" type="button"
                        data-rule-edit
                        data-family="${HF.escapeHtml(rule.family)}"
                        data-chain="${HF.escapeHtml(rule.chain)}"
                        data-rule-id="${HF.escapeHtml(rule.id)}"
                        title="${editTitle}"
                        ${editDisabled}>
                        Edit
                    </button>
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
        const filteredRules = chainRules
            .filter((rule) => rule.family === activeFamily)
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
            count.textContent = `${familyLabel(activeFamily)} rules=${filteredRules.length}`;
        }
        updatePagination(chain, pagination.page, totalPages, totalItems, startIndex, endIndex);
        if (!body) {
            return;
        }
        if (!visibleRules.length) {
            body.innerHTML = `
                <tr>
                    <td colspan="10">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no ${familyLabel(activeFamily)} ${HF.escapeHtml(chain)} NAT rules</span></div>
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
        updateMetric("#nat-summary-total", data.summary.total);
        updateMetric("#nat-summary-enabled", data.summary.enabled);
        updateMetric("#nat-summary-disabled", data.summary.disabled);
        updateMetric("#nat-summary-protected", data.summary.protected);
        NAT_CHAINS.forEach((chain) => renderChain(chain, chains[chain] || []));
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
                        <div class="terminal-empty"><span class="prompt">$</span><span>no NAT work requests</span></div>
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
            const data = await HF.fetchJson("/api/firewall/nat-rules");
            renderRules(data);
            setState("Ready");
        } catch (error) {
            setState("Offline");
            Object.entries(rulesBodies).forEach(([chain, body]) => {
                if (body) {
                    body.innerHTML = `
                        <tr>
                            <td colspan="10">
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
            const data = await HF.fetchJson("/api/firewall/nat-rules/work-requests");
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
            const result = await HF.fetchJson(`/api/firewall/nat-rules/${chain}/apply`, {
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
            const target = submitUrlAndMethod();
            const payload = payloadFromForm();
            const result = await HF.fetchJson(target.url, {
                method: target.method,
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            });
            setFormStatus(`saved=${result.rule_id}`);
            setActiveChain(payload.chain);
            ruleForm.reset();
            clearEditMode();
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
            const result = await HF.fetchJson(`/api/firewall/nat-rules/${family}/${chain}/${ruleId}/enabled`, {
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
            const result = await HF.fetchJson(`/api/firewall/nat-rules/${family}/${chain}/${ruleId}`, {
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

    document.querySelectorAll("[data-nat-tab]").forEach((tab) => {
        tab.addEventListener("click", () => setActiveTab(tab.dataset.natTab, true));
    });

    chainButtons.forEach((button) => {
        button.addEventListener("click", () => {
            setActiveChain(button.dataset.natChainTab);
            setActiveTab("rules", true);
        });
    });

    applyChainButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const chain = button.dataset.natChainApply;
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

    if (ruleForm) {
        ruleForm.addEventListener("submit", submitRule);
        ruleForm.addEventListener("reset", () => {
            clearEditMode();
            window.setTimeout(updateFormShape, 0);
        });
    }

    [familySelect, chainSelect, protocolSelect].forEach((element) => {
        if (element) {
            element.addEventListener("change", updateFormShape);
        }
    });

    Object.values(rulesBodies).forEach((body) => {
        if (body) {
            body.addEventListener("click", (event) => {
                const editButton = event.target.closest("[data-rule-edit]");
                const toggleButton = event.target.closest("[data-rule-toggle]");
                const deleteButton = event.target.closest("[data-rule-delete]");

                if (editButton) {
                    const rule = currentRulesByKey.get(ruleKey(editButton.dataset.family, editButton.dataset.chain, editButton.dataset.ruleId));
                    editRule(rule);
                    return;
                }
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
