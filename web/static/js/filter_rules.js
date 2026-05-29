(function () {
    const stateLabel = document.querySelector("#filter-rules-state");
    const formStatus = document.querySelector("#filter-form-status");
    const ruleForm = document.querySelector("#filter-rule-form");
    const rulesBodies = {
        INPUT: document.querySelector("#filter-input-body"),
        FORWARD: document.querySelector("#filter-forward-body"),
        OUTPUT: document.querySelector("#filter-output-body"),
    };
    const ruleCounts = {
        INPUT: document.querySelector("#filter-input-count"),
        FORWARD: document.querySelector("#filter-forward-count"),
        OUTPUT: document.querySelector("#filter-output-count"),
    };
    const policySelects = {
        INPUT: document.querySelector("[data-chain-policy='INPUT']"),
        FORWARD: document.querySelector("[data-chain-policy='FORWARD']"),
        OUTPUT: document.querySelector("[data-chain-policy='OUTPUT']"),
    };
    const workRequestsBody = document.querySelector("#filter-work-requests-body");
    const workRequestsCount = document.querySelector("#filter-work-requests-count");
    const submitButton = document.querySelector("#filter-submit-button");
    const applyModal = document.querySelector("#filter-apply-modal");
    const applyChainLabel = document.querySelector("#filter-apply-chain");
    const applyMessage = document.querySelector("#filter-apply-message");
    const applyConfirmButton = document.querySelector("[data-apply-confirm]");
    const deleteModal = document.querySelector("#filter-delete-modal");
    const deleteRuleLabel = document.querySelector("#filter-delete-rule");
    const deleteMessage = document.querySelector("#filter-delete-message");
    const deleteConfirmButton = document.querySelector("[data-delete-confirm]");
    const familySelect = document.querySelector("#filter-family");
    const chainSelect = document.querySelector("#filter-chain");
    const protocolSelect = document.querySelector("#filter-protocol");
    const ifaceInSelect = document.querySelector("#filter-iface-in");
    const ifaceOutSelect = document.querySelector("#filter-iface-out");
    const icmpTypeSelect = document.querySelector("#filter-icmp-type");
    const icmpCodeSelect = document.querySelector("#filter-icmp-code");
    const srcAddr = document.querySelector("#filter-src-addr");
    const dstAddr = document.querySelector("#filter-dst-addr");
    let currentRulesByKey = new Map();
    let currentPolicies = {};
    let currentRulesData = null;
    let selectedRuleFamily = "IPV4";
    let editingRule = null;
    let pendingApplyChain = "";
    let pendingDeleteButton = null;
    let workRequestsPoller = null;
    let workRequestsLoading = false;
    const WORK_REQUESTS_POLL_MS = 3000;
    const ICMP_TYPES = {
        IPV4: [
            {value: "", label: "any"},
            {value: "0", label: "Echo reply"},
            {value: "3", label: "Destination unreachable"},
            {value: "5", label: "Redirect"},
            {value: "8", label: "Echo request"},
            {value: "9", label: "Router advertisement"},
            {value: "10", label: "Router solicitation"},
            {value: "11", label: "Time exceeded"},
            {value: "12", label: "Parameter problem"},
            {value: "13", label: "Timestamp request"},
            {value: "14", label: "Timestamp reply"},
            {value: "17", label: "Address mask request"},
            {value: "18", label: "Address mask reply"},
        ],
        IPV6: [
            {value: "", label: "any"},
            {value: "1", label: "Destination unreachable"},
            {value: "2", label: "Packet too big"},
            {value: "3", label: "Time exceeded"},
            {value: "4", label: "Parameter problem"},
            {value: "128", label: "Echo request"},
            {value: "129", label: "Echo reply"},
            {value: "133", label: "Router solicitation"},
            {value: "134", label: "Router advertisement"},
            {value: "135", label: "Neighbor solicitation"},
            {value: "136", label: "Neighbor advertisement"},
            {value: "137", label: "Redirect"},
        ],
    };
    const ICMP_CODES = {
        IPV4: {
            "": [{value: "", label: "any"}],
            0: [{value: "0", label: "No code"}],
            3: [
                {value: "0", label: "Network unreachable"},
                {value: "1", label: "Host unreachable"},
                {value: "2", label: "Protocol unreachable"},
                {value: "3", label: "Port unreachable"},
                {value: "4", label: "Fragmentation needed"},
                {value: "5", label: "Source route failed"},
                {value: "6", label: "Destination network unknown"},
                {value: "7", label: "Destination host unknown"},
                {value: "9", label: "Network administratively prohibited"},
                {value: "10", label: "Host administratively prohibited"},
                {value: "13", label: "Communication administratively prohibited"},
            ],
            5: [
                {value: "0", label: "Redirect network"},
                {value: "1", label: "Redirect host"},
                {value: "2", label: "Redirect TOS and network"},
                {value: "3", label: "Redirect TOS and host"},
            ],
            8: [{value: "0", label: "No code"}],
            9: [{value: "0", label: "No code"}],
            10: [{value: "0", label: "No code"}],
            11: [
                {value: "0", label: "TTL exceeded in transit"},
                {value: "1", label: "Fragment reassembly time exceeded"},
            ],
            12: [
                {value: "0", label: "Pointer indicates error"},
                {value: "1", label: "Missing required option"},
                {value: "2", label: "Bad length"},
            ],
            13: [{value: "0", label: "No code"}],
            14: [{value: "0", label: "No code"}],
            17: [{value: "0", label: "No code"}],
            18: [{value: "0", label: "No code"}],
        },
        IPV6: {
            "": [{value: "", label: "any"}],
            1: [
                {value: "0", label: "No route to destination"},
                {value: "1", label: "Communication administratively prohibited"},
                {value: "2", label: "Beyond scope of source address"},
                {value: "3", label: "Address unreachable"},
                {value: "4", label: "Port unreachable"},
                {value: "5", label: "Source address failed policy"},
                {value: "6", label: "Reject route to destination"},
            ],
            2: [{value: "0", label: "No code"}],
            3: [
                {value: "0", label: "Hop limit exceeded in transit"},
                {value: "1", label: "Fragment reassembly time exceeded"},
            ],
            4: [
                {value: "0", label: "Erroneous header field"},
                {value: "1", label: "Unrecognized next header"},
                {value: "2", label: "Unrecognized IPv6 option"},
            ],
            128: [{value: "0", label: "No code"}],
            129: [{value: "0", label: "No code"}],
            133: [{value: "0", label: "No code"}],
            134: [{value: "0", label: "No code"}],
            135: [{value: "0", label: "No code"}],
            136: [{value: "0", label: "No code"}],
            137: [{value: "0", label: "No code"}],
        },
    };

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

    function updateMetric(id, value) {
        const element = document.querySelector(id);
        if (element) {
            element.textContent = HF.number(value).toLocaleString();
        }
    }

    function ruleKey(family, chain, ruleId) {
        return `${family}:${chain}:${ruleId}`;
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

    function setFieldHidden(field, shouldHide) {
        field.hidden = shouldHide;
        field.classList.toggle("is-hidden", shouldHide);
        field.querySelectorAll("select, input").forEach((element) => {
            element.disabled = shouldHide;
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

    function setActiveTab(tabName, refreshData = false) {
        document.querySelectorAll("[data-filter-tab]").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.filterTab === tabName);
        });
        document.querySelectorAll("[data-filter-view]").forEach((view) => {
            view.hidden = view.dataset.filterView !== tabName;
        });
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

    function portLabel(port) {
        return port === null || port === undefined || port === "" || Number(port) === 0 ? "*" : String(port);
    }

    function protocolFormValue(rule) {
        if (rule.protocol_name === "icmpv6") {
            return "icmp";
        }
        return rule.protocol_name || "tcp";
    }

    function conntrackModeFromRule(rule) {
        if (HF.number(rule.ct_established) === 1 && HF.number(rule.ct_related) === 1) {
            return "established-related";
        }
        if (HF.number(rule.ct_new) === 1) {
            return "new";
        }
        return "";
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
        if (rule.chain === "INPUT") {
            return `in=${HF.escapeHtml(rule.iface_in)}`;
        }
        if (rule.chain === "OUTPUT") {
            return `out=${HF.escapeHtml(rule.iface_out)}`;
        }
        return `in=${HF.escapeHtml(rule.iface_in)}<br>out=${HF.escapeHtml(rule.iface_out)}`;
    }

    function endpointLabel(rule, prefix) {
        const addr = rule[`${prefix}_addr`];
        const port = rule[`${prefix}_port`];
        return `${HF.escapeHtml(addr)}<br><span class="muted">port=${HF.escapeHtml(portLabel(port))}</span>`;
    }

    function ruleRow(rule) {
        const enabled = HF.number(rule.enabled) === 1;
        const applied = HF.number(rule.applied) === 1;
        const pendingDelete = HF.number(rule.pending_delete) === 1;
        const protectedRule = HF.number(rule.protected) === 1;
        const statusClass = pendingDelete ? "down" : !enabled ? "disabled" : applied ? "up" : "down";
        const statusLabel = pendingDelete ? "PENDING DELETE" : !enabled ? "DISABLED" : applied ? "ACTIVE" : "PENDING APPLY";
        const nextEnabled = enabled ? 0 : 1;
        const buttonLabel = enabled ? "Disable" : "Enable";
        const protectedBadge = protectedRule ? '<span class="status protected">PROTECTED</span>' : "";
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
                <td><strong>${HF.escapeHtml(rule.action)}</strong></td>
                <td>${interfaceLabel(rule)}</td>
                <td>${HF.escapeHtml(rule.protocol_name)}</td>
                <td>${endpointLabel(rule, "src")}</td>
                <td>${endpointLabel(rule, "dst")}</td>
                <td>${HF.escapeHtml(conntrackLabel(rule))}</td>
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

    function renderChain(chain, rules) {
        const body = rulesBodies[chain];
        const count = ruleCounts[chain];
        const allChainRules = rules || [];
        const chainRules = allChainRules.filter((rule) => rule.family === selectedRuleFamily);

        if (count) {
            count.textContent = `rules=${chainRules.length}`;
        }
        if (!body) {
            return;
        }
        if (!chainRules.length) {
            body.innerHTML = `
                <tr>
                    <td colspan="10">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no ${HF.escapeHtml(selectedRuleFamily)} ${HF.escapeHtml(chain)} rules</span></div>
                    </td>
                </tr>
            `;
            return;
        }
        body.innerHTML = chainRules.map(ruleRow).join("");
    }

    function policyValueForChain(policies, chain, family = selectedRuleFamily) {
        const chainPolicies = policies && policies[chain] ? policies[chain] : {};
        const familyPolicy = chainPolicies[family] ? chainPolicies[family].policy : "";
        return familyPolicy || "DROP";
    }

    function renderPolicies(policies) {
        currentPolicies = policies || {};
        Object.entries(policySelects).forEach(([chain, select]) => {
            if (select) {
                select.value = policyValueForChain(currentPolicies, chain);
            }
        });
    }

    function renderRules(data) {
        const chains = data.chains || {};
        const selectedRules = (data.rules || []).filter((rule) => rule.family === selectedRuleFamily);
        currentRulesByKey = new Map();
        currentRulesData = data;
        (data.rules || []).forEach((rule) => {
            currentRulesByKey.set(ruleKey(rule.family, rule.chain, rule.id), rule);
        });
        updateMetric("#filter-summary-total", selectedRules.length);
        updateMetric("#filter-summary-enabled", selectedRules.filter((rule) => HF.number(rule.enabled) === 1).length);
        updateMetric("#filter-summary-disabled", selectedRules.filter((rule) => HF.number(rule.enabled) !== 1).length);
        updateMetric("#filter-summary-protected", selectedRules.filter((rule) => HF.number(rule.protected) === 1).length);
        renderPolicies(data.policies || {});
        ["INPUT", "FORWARD", "OUTPUT"].forEach((chain) => renderChain(chain, chains[chain] || []));
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
                        <div class="terminal-empty"><span class="prompt">$</span><span>no filter work requests</span></div>
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

    function interfaceOptionLabel(iface) {
        const role = iface.role || "UNKNOWN";
        const state = HF.number(iface.is_actived) === 1 ? "UP" : "DOWN";
        const mac = iface.mac_address || "no-mac";
        return `${iface.name} (${role}, ${state}, ${mac})`;
    }

    function renderInterfaceChoices(interfaces) {
        const ifaceInOptions = [
            {value: "", label: "select interface"},
            {value: "ANY", label: "ANY"},
        ].concat(
            interfaces.map((iface) => ({
                value: iface.name,
                label: interfaceOptionLabel(iface),
            })),
        );
        const ifaceOutOptions = [{value: "", label: "select interface"}].concat(
            interfaces.map((iface) => ({
                value: iface.name,
                label: interfaceOptionLabel(iface),
            })),
        );
        replaceOptions(ifaceInSelect, ifaceInOptions);
        replaceOptions(ifaceOutSelect, ifaceOutOptions);
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

    function updateIcmpChoices() {
        const family = familySelect ? familySelect.value : "IPV4";
        const selectedType = icmpTypeSelect ? icmpTypeSelect.value : "";
        const typeOptions = ICMP_TYPES[family] || ICMP_TYPES.IPV4;
        const typeStillExists = typeOptions.some((item) => item.value === selectedType);

        replaceOptions(icmpTypeSelect, typeOptions);
        if (icmpTypeSelect) {
            icmpTypeSelect.value = typeStillExists ? selectedType : "";
        }

        const codeOptions = (ICMP_CODES[family] || ICMP_CODES.IPV4)[icmpTypeSelect ? icmpTypeSelect.value : ""] || [{value: "0", label: "No code"}];
        replaceOptions(icmpCodeSelect, codeOptions);
    }

    function updateFormShape() {
        const family = familySelect ? familySelect.value : "IPV4";
        const chain = chainSelect ? chainSelect.value : "INPUT";
        const protocol = protocolSelect ? protocolSelect.value : "tcp";
        const isIcmp = protocol === "icmp";
        const isAll = protocol === "all";
        const hasPorts = ["tcp", "udp"].includes(protocol);
        const wildcard = family === "IPV6" ? "::/0" : "0.0.0.0/0";

        if (srcAddr && (srcAddr.value === "" || srcAddr.value === "0.0.0.0/0" || srcAddr.value === "::/0")) {
            srcAddr.value = wildcard;
        }
        if (dstAddr && (dstAddr.value === "" || dstAddr.value === "0.0.0.0/0" || dstAddr.value === "::/0")) {
            dstAddr.value = wildcard;
        }

        document.querySelectorAll("[data-iface-in-field]").forEach((field) => {
            setFieldHidden(field, chain === "OUTPUT");
        });
        document.querySelectorAll("[data-iface-out-field]").forEach((field) => {
            setFieldHidden(field, chain === "INPUT");
        });
        document.querySelectorAll("[data-port-field]").forEach((field) => {
            setFieldHidden(field, !hasPorts);
        });
        document.querySelectorAll("[data-icmp-field]").forEach((field) => {
            setFieldHidden(field, !isIcmp);
        });
        updateIcmpChoices();
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

    function submitUrlAndMethod() {
        if (!editingRule) {
            return {url: "/api/firewall/filter-rules", method: "POST"};
        }
        return {
            url: `/api/firewall/filter-rules/${editingRule.family}/${editingRule.chain}/${editingRule.id}`,
            method: "PUT",
        };
    }

    function setFormMode(rule) {
        editingRule = rule;
        if (submitButton) {
            submitButton.textContent = rule ? "Save rule" : "Queue rule";
        }
        setFormStatus(rule ? `editing=${rule.family}/${rule.chain}/${rule.id}` : "queue=idle");
    }

    function clearEditMode() {
        setFormMode(null);
    }

    function editRule(rule) {
        if (!rule || HF.number(rule.protected) === 1) {
            return;
        }

        setSelectValue(familySelect, rule.family);
        setSelectValue(chainSelect, rule.chain);
        setSelectValue(protocolSelect, protocolFormValue(rule));
        setSelectValue(ruleForm.elements.action, rule.action);
        setSelectValue(ifaceInSelect, rule.iface_in);
        setSelectValue(ifaceOutSelect, rule.iface_out);
        setSelectValue(ruleForm.elements.enabled, rule.enabled);
        setSelectValue(ruleForm.elements.conntrack_mode, conntrackModeFromRule(rule));

        ruleForm.elements.src_addr.value = rule.src_addr || defaultAddressForFamily(rule.family);
        ruleForm.elements.dst_addr.value = rule.dst_addr || defaultAddressForFamily(rule.family);
        if (ruleForm.elements.src_port) {
            ruleForm.elements.src_port.value = rule.src_port === null || rule.src_port === undefined ? 0 : rule.src_port;
        }
        if (ruleForm.elements.dst_port) {
            ruleForm.elements.dst_port.value = rule.dst_port === null || rule.dst_port === undefined ? 0 : rule.dst_port;
        }

        updateFormShape();
        setSelectValue(icmpTypeSelect, rule.protocol_type);
        updateIcmpChoices();
        setSelectValue(icmpCodeSelect, rule.protocol_code);
        setFormMode(rule);
        setActiveTab("new-rule");
    }

    function defaultAddressForFamily(family) {
        return family === "IPV6" ? "::/0" : "0.0.0.0/0";
    }

    function openApplyModal(chain) {
        pendingApplyChain = chain;
        const chainRules = Array.from(currentRulesByKey.values()).filter((rule) => rule.chain === chain && rule.family === selectedRuleFamily);
        const enabledCount = chainRules.filter((rule) => HF.number(rule.enabled) === 1).length;
        const policy = policyValueForChain(currentPolicies, chain);

        if (applyChainLabel) {
            applyChainLabel.textContent = `family=${selectedRuleFamily} chain=${chain}`;
        }
        if (applyMessage) {
            applyMessage.textContent = `Are you sure you want to apply ${enabledCount} enabled ${selectedRuleFamily} rule(s) from the ${chain} chain with policy=${policy}?`;
        }
        if (applyModal) {
            applyModal.hidden = false;
        }
    }

    function closeApplyModal() {
        pendingApplyChain = "";
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
            const data = await HF.fetchJson("/api/firewall/filter-rules");
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
            const data = await HF.fetchJson("/api/firewall/filter-rules/work-requests");
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

    async function submitRule(event) {
        event.preventDefault();
        try {
            setFormStatus("queue=writing");
            const target = submitUrlAndMethod();
            const result = await HF.fetchJson(target.url, {
                method: target.method,
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payloadFromForm()),
            });
            setFormStatus(`saved=${result.rule_id}`);
            ruleForm.reset();
            clearEditMode();
            updateFormShape();
            setActiveTab("rules", true);
        } catch (error) {
            setFormStatus(`error=${error.message}`);
        }
    }

    async function applyChain() {
        if (!pendingApplyChain) {
            return;
        }
        try {
            if (applyConfirmButton) {
                applyConfirmButton.disabled = true;
            }
            setFormStatus("queue=writing");
            const chain = pendingApplyChain;
            const result = await HF.fetchJson(`/api/firewall/filter-rules/${chain}/apply`, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({family: selectedRuleFamily}),
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

    async function toggleRule(button) {
        try {
            button.disabled = true;
            setFormStatus("queue=writing");
            const family = button.dataset.family;
            const chain = button.dataset.chain;
            const ruleId = button.dataset.ruleId;
            const enabled = Number(button.dataset.enabled);
            const result = await HF.fetchJson(`/api/firewall/filter-rules/${family}/${chain}/${ruleId}/enabled`, {
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

    async function saveChainPolicy(select) {
        const chain = select.dataset.chainPolicy;
        const policy = select.value;
        try {
            select.disabled = true;
            setFormStatus("policy=saving");
            const result = await HF.fetchJson(`/api/firewall/filter-rules/${chain}/policy`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({family: selectedRuleFamily, policy}),
            });
            setFormStatus(`policy=${result.family}/${result.policy}`);
            await loadRules();
        } catch (error) {
            setFormStatus(`error=${error.message}`);
            renderPolicies(currentPolicies);
        } finally {
            select.disabled = false;
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
            const result = await HF.fetchJson(`/api/firewall/filter-rules/${family}/${chain}/${ruleId}`, {
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

    document.querySelectorAll("[data-filter-tab]").forEach((tab) => {
        tab.addEventListener("click", () => setActiveTab(tab.dataset.filterTab, true));
    });

    document.querySelectorAll("[data-filter-family-tab]").forEach((tab) => {
        tab.addEventListener("click", () => {
            selectedRuleFamily = tab.dataset.filterFamilyTab || "IPV4";
            document.querySelectorAll("[data-filter-family-tab]").forEach((item) => {
                item.classList.toggle("active", item.dataset.filterFamilyTab === selectedRuleFamily);
            });
            if (currentRulesData) {
                renderRules(currentRulesData);
            }
        });
    });

    Object.values(policySelects).forEach((select) => {
        if (select) {
            select.addEventListener("change", () => saveChainPolicy(select));
        }
    });

    document.querySelectorAll("[data-chain-apply]").forEach((button) => {
        button.addEventListener("click", () => openApplyModal(button.dataset.chainApply));
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

    if (icmpTypeSelect) {
        icmpTypeSelect.addEventListener("change", updateIcmpChoices);
    }

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
    setActiveTab("rules");
    loadInterfaceChoices();
    loadRules();
}());
