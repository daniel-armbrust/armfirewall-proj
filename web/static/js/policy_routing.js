(function () {
    const stateLabel = document.querySelector("#policy-routing-state");
    const routeForm = document.querySelector("#policy-route-form");
    const ruleForm = document.querySelector("#policy-rule-form");
    const tableForm = document.querySelector("#policy-table-form");
    const routeStatus = document.querySelector("#policy-route-form-status");
    const ruleStatus = document.querySelector("#policy-rule-form-status");
    const tableStatus = document.querySelector("#policy-table-form-status");
    const routesBody = document.querySelector("#policy-routes-body");
    const rulesBody = document.querySelector("#policy-rules-body");
    const tablesBody = document.querySelector("#policy-tables-body");
    const workRequestsBody = document.querySelector("#policy-work-requests-body");
    const workRequestsCount = document.querySelector("#policy-work-requests-count");
    const applyModal = document.querySelector("#policy-apply-modal");
    const deleteModal = document.querySelector("#policy-delete-modal");
    const deleteItemLabel = document.querySelector("#policy-delete-item");
    const deleteMessage = document.querySelector("#policy-delete-message");
    const applyConfirmButton = document.querySelector("[data-apply-confirm]");
    const deleteConfirmButton = document.querySelector("[data-delete-confirm]");
    const routeTableSelect = document.querySelector("#policy-route-table");
    const ruleTableSelect = document.querySelector("#policy-rule-table");
    const ruleActionSelect = document.querySelector("#policy-rule-action");
    const routeFamilySelect = document.querySelector("#policy-route-family");
    const ruleFamilySelect = document.querySelector("#policy-rule-family");
    const routeDevSelect = document.querySelector("#policy-route-dev");
    const ruleIifSelect = document.querySelector("#policy-rule-iif");
    const ruleOifSelect = document.querySelector("#policy-rule-oif");
    const familyFilterSelect = document.querySelector("#policy-family-filter");
    const tableFilterSelect = document.querySelector("#policy-table-filter");
    const ruleFamilyFilterSelect = document.querySelector("#policy-rule-family-filter");
    const ruleTableFilterSelect = document.querySelector("#policy-rule-table-filter");
    const pageStatusLabels = {
        routes: document.querySelector("[data-policy-page-status='routes']"),
        rules: document.querySelector("[data-policy-page-status='rules']"),
        tables: document.querySelector("[data-policy-page-status='tables']"),
    };
    const pagePrevButtons = {
        routes: document.querySelector("[data-policy-page-prev='routes']"),
        rules: document.querySelector("[data-policy-page-prev='rules']"),
        tables: document.querySelector("[data-policy-page-prev='tables']"),
    };
    const pageNextButtons = {
        routes: document.querySelector("[data-policy-page-next='routes']"),
        rules: document.querySelector("[data-policy-page-next='rules']"),
        tables: document.querySelector("[data-policy-page-next='tables']"),
    };
    const pageSizeSelects = {
        routes: document.querySelector("[data-policy-page-size='routes']"),
        rules: document.querySelector("[data-policy-page-size='rules']"),
        tables: document.querySelector("[data-policy-page-size='tables']"),
    };
    const familyButtons = Array.from(document.querySelectorAll("[data-policy-family]"));
    const createButtons = Array.from(document.querySelectorAll("[data-policy-create-for]"));
    let currentData = {tables: [], routes: [], rules: []};
    let pendingDelete = null;
    let workRequestsPoller = null;
    let workRequestsLoading = false;
    let interfaceDescriptions = new Map();
    let interfaceRoles = new Map();
    let activeFamily = "ipv4";
    let activeRouteTable = "";
    let activeRuleFamily = "ipv4";
    let activeRuleTable = "";
    const viewPagination = {
        routes: {page: 1, pageSize: 25},
        rules: {page: 1, pageSize: 25},
        tables: {page: 1, pageSize: 25},
    };
    const WORK_REQUESTS_POLL_MS = 3000;
    const PROTECTED_ROUTE_TABLE_IDS = new Set([253, 255]);

    function setState(value) {
        if (stateLabel) {
            stateLabel.textContent = value;
        }
    }

    function setStatus(element, value) {
        if (element) {
            element.textContent = value;
        }
    }

    function numberValue(value) {
        return HF.number(value);
    }

    function setMetric(id, value) {
        const element = document.querySelector(id);
        if (element) {
            element.textContent = numberValue(value).toLocaleString();
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
            if (item.title) {
                option.title = item.title;
            }
            select.appendChild(option);
        });
    }

    function tableLabel(table) {
        return `${table.table_id} ${table.table_name}`;
    }

    function refreshTableChoices() {
        const tables = currentData.tables.filter((table) => numberValue(table.enabled) === 1 && numberValue(table.pending_delete) === 0);
        const routeOptions = tables
            .filter((table) => !PROTECTED_ROUTE_TABLE_IDS.has(numberValue(table.table_id)))
            .map((table) => ({value: table.table_id, label: tableLabel(table)}));
        const ruleOptions = tables
            .filter((table) => !PROTECTED_ROUTE_TABLE_IDS.has(numberValue(table.table_id)))
            .map((table) => ({value: table.table_id, label: tableLabel(table)}));
        replaceOptions(routeTableSelect, routeOptions);
        replaceOptions(ruleTableSelect, ruleOptions);
    }

    function refreshRouteTableFilter() {
        if (!tableFilterSelect) {
            return;
        }
        const currentValue = activeRouteTable;
        const tables = (currentData.tables || [])
            .filter((table) => numberValue(table.enabled) === 1 && numberValue(table.pending_delete) === 0)
            .map((table) => ({value: String(table.table_id), label: tableLabel(table)}));
        replaceOptions(tableFilterSelect, tables);
        const values = new Set(Array.from(tableFilterSelect.options).map((option) => option.value));
        const mainTable = tables.find((table) => String(table.label || "").toLowerCase().endsWith(" main"));
        activeRouteTable = values.has(currentValue) ? currentValue : (mainTable?.value || tables[0]?.value || "");
        tableFilterSelect.value = activeRouteTable;
    }

    function refreshRuleTableFilter() {
        if (!ruleTableFilterSelect) {
            return;
        }
        const currentValue = activeRuleTable;
        const tables = (currentData.tables || [])
            .filter((table) => numberValue(table.enabled) === 1 && numberValue(table.pending_delete) === 0)
            .map((table) => ({value: String(table.table_id), label: tableLabel(table)}));
        replaceOptions(ruleTableFilterSelect, tables);
        const values = new Set(Array.from(ruleTableFilterSelect.options).map((option) => option.value));
        const mainTable = tables.find((table) => String(table.label || "").toLowerCase().endsWith(" main"));
        activeRuleTable = values.has(currentValue) ? currentValue : (mainTable?.value || tables[0]?.value || "");
        ruleTableFilterSelect.value = activeRuleTable;
    }

    function interfaceOptionLabel(iface) {
        const role = iface.role || "UNKNOWN";
        const state = numberValue(iface.is_actived) === 1 ? "UP" : "DOWN";
        return `${iface.name} (${role}, ${state})`;
    }

    function interfaceDescription(name) {
        return interfaceDescriptions.get(String(name || "")) || "";
    }

    function interfaceRole(name) {
        const value = String(name || "");
        return interfaceRoles.get(value) || (value ? "UNKNOWN" : "-");
    }

    function interfaceName(name) {
        const value = String(name || "");
        if (!value) {
            return "-";
        }
        const description = interfaceDescription(value);
        const tooltip = description ? ` title="${HF.escapeHtml(description)}" data-tooltip="${HF.escapeHtml(description)}" tabindex="0"` : "";
        return `<span class="iface-tooltip"${tooltip}>${HF.escapeHtml(value)}</span>`;
    }

    async function loadInterfaceChoices() {
        try {
            const data = await HF.fetchJson("/api/interfaces");
            interfaceDescriptions = new Map(
                (data.interfaces || []).map((iface) => [String(iface.name || ""), String(iface.description || "")]),
            );
            interfaceRoles = new Map(
                (data.interfaces || []).map((iface) => [String(iface.name || ""), String(iface.role || "UNKNOWN")]),
            );
            const options = [{value: "", label: "optional"}].concat(
                (data.interfaces || []).map((iface) => ({
                    value: iface.name,
                    label: interfaceOptionLabel(iface),
                    title: iface.description || "",
                })),
            );
            replaceOptions(routeDevSelect, options);
            replaceOptions(ruleIifSelect, options);
            replaceOptions(ruleOifSelect, options);
            if (currentData.summary) {
                renderData(currentData);
            }
        } catch (error) {
            const options = [{value: "", label: `interfaces unavailable: ${error.message}`}];
            replaceOptions(routeDevSelect, options);
            replaceOptions(ruleIifSelect, options);
            replaceOptions(ruleOifSelect, options);
        }
    }

    function updateRuleFormShape() {
        const action = ruleActionSelect ? ruleActionSelect.value : "lookup";
        document.querySelectorAll("[data-rule-table-field]").forEach((field) => {
            const hide = action !== "lookup";
            field.hidden = hide;
            field.classList.toggle("is-hidden", hide);
            field.querySelectorAll("select, input").forEach((element) => {
                element.disabled = hide;
            });
        });
    }

    function itemStatus(item) {
        if (numberValue(item.pending_delete) === 1) {
            return {label: "PENDING DELETE", className: "down"};
        }
        if (numberValue(item.enabled) === 0) {
            return {label: "DISABLED", className: "disabled"};
        }
        if (numberValue(item.applied) === 1) {
            return {label: "ACTIVE", className: "up"};
        }
        return {label: "PENDING APPLY", className: "down"};
    }

    function policyItemProtected(item) {
        return numberValue(item.protected) === 1 || PROTECTED_ROUTE_TABLE_IDS.has(numberValue(item.table_id));
    }

    function protectedBadge(item) {
        return policyItemProtected(item) ? '<span class="status protected">PROTECTED</span>' : "";
    }

    function familyLabel(family) {
        return String(family || "").toLowerCase() === "ipv6" ? "IPv6" : "IPv4";
    }

    function setSelectValue(select, value) {
        if (select) {
            select.value = value;
        }
    }

    function familyMatches(item) {
        return String(item.addr_family || "ipv4").toLowerCase() === activeFamily;
    }

    function routeTableMatches(route) {
        return activeRouteTable !== "" && String(route.table_id) === activeRouteTable;
    }

    function filteredRoutes() {
        return (currentData.routes || []).filter((route) => familyMatches(route) && routeTableMatches(route));
    }

    function filteredRules() {
        return (currentData.rules || []).filter((rule) => {
            const family = String(rule.addr_family || "ipv4").toLowerCase();
            return family === activeRuleFamily && activeRuleTable !== "" && String(rule.table_id) === activeRuleTable;
        });
    }

    function updatePagination(kind, page, totalPages, totalItems, startIndex, endIndex) {
        const status = pageStatusLabels[kind];
        const prev = pagePrevButtons[kind];
        const next = pageNextButtons[kind];
        if (status) {
            const firstItem = totalItems ? startIndex + 1 : 0;
            const lastItem = totalItems ? endIndex : 0;
            status.textContent = `Page ${page} of ${totalPages} (${firstItem} - ${lastItem} of ${totalItems} total items)`;
        }
        if (prev) {
            prev.disabled = page <= 1;
        }
        if (next) {
            next.disabled = page >= totalPages;
        }
    }

    function pagedItems(kind, items) {
        const pagination = viewPagination[kind] || {page: 1, pageSize: 25};
        const totalItems = items.length;
        const totalPages = Math.max(1, Math.ceil(totalItems / pagination.pageSize));
        pagination.page = Math.min(Math.max(1, pagination.page), totalPages);
        const startIndex = totalItems ? (pagination.page - 1) * pagination.pageSize : 0;
        const endIndex = Math.min(startIndex + pagination.pageSize, totalItems);
        updatePagination(kind, pagination.page, totalPages, totalItems, startIndex, endIndex);
        return items.slice(startIndex, endIndex);
    }

    function setPolicyFormFamily() {
        setSelectValue(routeFamilySelect, activeFamily);
        setSelectValue(ruleFamilySelect, activeRuleFamily);
    }

    function setActiveFamily(family) {
        activeFamily = String(family || "ipv4").toLowerCase() === "ipv6" ? "ipv6" : "ipv4";
        viewPagination.routes.page = 1;
        familyButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.policyFamily === activeFamily);
        });
        if (familyFilterSelect) {
            familyFilterSelect.value = activeFamily;
        }
        setPolicyFormFamily();
        if (currentData.summary) {
            renderData(currentData);
        }
    }

    function setActiveRuleFamily(family) {
        activeRuleFamily = String(family || "ipv4").toLowerCase() === "ipv6" ? "ipv6" : "ipv4";
        viewPagination.rules.page = 1;
        if (ruleFamilyFilterSelect) {
            ruleFamilyFilterSelect.value = activeRuleFamily;
        }
        setSelectValue(ruleFamilySelect, activeRuleFamily);
        if (currentData.summary) {
            renderData(currentData);
        }
    }

    function setActiveRouteTable(tableId) {
        activeRouteTable = String(tableId || "");
        viewPagination.routes.page = 1;
        if (tableFilterSelect) {
            tableFilterSelect.value = activeRouteTable;
        }
        if (currentData.summary) {
            renderData(currentData);
        }
    }

    function setActiveRuleTable(tableId) {
        activeRuleTable = String(tableId || "");
        viewPagination.rules.page = 1;
        if (ruleTableFilterSelect) {
            ruleTableFilterSelect.value = activeRuleTable;
        }
        if (currentData.summary) {
            renderData(currentData);
        }
    }

    function tableGroupLabel(item) {
        if (item.table_name) {
            return `${item.table_name} (${item.table_id})`;
        }
        if (item.table_id !== null && item.table_id !== undefined && String(item.table_id) !== "") {
            return `table ${item.table_id}`;
        }
        return "no table";
    }

    function groupedRows(items, rowRenderer, colspan) {
        const groups = new Map();
        items.forEach((item) => {
            const family = String(item.addr_family || "ipv4").toLowerCase();
            const tableKey = `${item.table_id ?? "none"}:${item.table_name || ""}`;
            if (!groups.has(family)) {
                groups.set(family, new Map());
            }
            if (!groups.get(family).has(tableKey)) {
                groups.get(family).set(tableKey, []);
            }
            groups.get(family).get(tableKey).push(item);
        });

        return ["ipv4", "ipv6"].map((family) => {
            const tableGroups = groups.get(family);
            if (!tableGroups) {
                return "";
            }
            const total = Array.from(tableGroups.values()).reduce((sum, rows) => sum + rows.length, 0);
            const familyRow = `
                <tr class="policy-family-row">
                    <td colspan="${colspan}">${familyLabel(family)} <span>${total} item${total === 1 ? "" : "s"}</span></td>
                </tr>
            `;
            const tableRows = Array.from(tableGroups.values()).map((rows) => {
                const first = rows[0];
                return `
                    <tr class="policy-table-row">
                        <td colspan="${colspan}">${HF.escapeHtml(tableGroupLabel(first))} <span>${rows.length} item${rows.length === 1 ? "" : "s"}</span></td>
                    </tr>
                    ${rows.map(rowRenderer).join("")}
                `;
            }).join("");
            return familyRow + tableRows;
        }).join("");
    }

    function routeRow(route) {
        const status = itemStatus(route);
        const pending = numberValue(route.pending_delete) === 1;
        const protectedItem = policyItemProtected(route);
        const enabled = numberValue(route.enabled) === 1;
        const toggleDisabled = pending || (enabled && protectedItem) ? "disabled" : "";
        const deleteDisabled = pending || protectedItem || !enabled ? "disabled" : "";
        const nextEnabled = enabled ? 0 : 1;
        const buttonLabel = enabled ? "Disable" : "Enable";
        return `
            <tr>
                <td>${HF.escapeHtml(route.route_order)}</td>
                <td>${HF.escapeHtml(route.route_type)}</td>
                <td>${HF.escapeHtml(route.destination)}</td>
                <td>${HF.escapeHtml(route.gateway || "-")}</td>
                <td>${interfaceName(route.dev)}</td>
                <td><span class="role">${HF.escapeHtml(interfaceRole(route.dev))}</span></td>
                <td>${HF.escapeHtml(route.metric ?? "-")}</td>
                <td><span class="status ${status.className}">${status.label}</span>${protectedBadge(route)}</td>
                <td>
                    <button class="text-button compact" type="button" data-policy-toggle data-kind="routes"
                        data-id="${HF.escapeHtml(route.id)}" data-enabled="${nextEnabled}" ${toggleDisabled}>${buttonLabel}</button>
                    <button class="text-button compact danger" type="button" data-policy-delete data-kind="routes"
                        data-id="${HF.escapeHtml(route.id)}" ${deleteDisabled}>Delete</button>
                </td>
            </tr>
        `;
    }

    function ruleSelector(rule) {
        const values = [];
        if (rule.source_addr) values.push(`from=${rule.source_addr}`);
        if (rule.destination_addr) values.push(`to=${rule.destination_addr}`);
        if (rule.ip_proto) values.push(`proto=${rule.ip_proto}`);
        if (rule.sport) values.push(`sport=${rule.sport}`);
        if (rule.dport) values.push(`dport=${rule.dport}`);
        return values.length ? values.join("<br>") : "-";
    }

    function ruleRow(rule) {
        const status = itemStatus(rule);
        const pending = numberValue(rule.pending_delete) === 1;
        const protectedItem = numberValue(rule.protected) === 1;
        const enabled = numberValue(rule.enabled) === 1;
        const toggleDisabled = pending || (enabled && protectedItem) ? "disabled" : "";
        const deleteDisabled = pending || protectedItem || !enabled ? "disabled" : "";
        const nextEnabled = enabled ? 0 : 1;
        const buttonLabel = enabled ? "Disable" : "Enable";
        const mark = rule.fwmark ? `${rule.fwmark}${rule.fwmask ? `/${rule.fwmask}` : ""}` : "-";
        return `
            <tr>
                <td>${HF.escapeHtml(rule.priority)}</td>
                <td>${ruleSelector(rule)}</td>
                <td>iif=${rule.incoming_iface ? interfaceName(rule.incoming_iface) : "*"}<br>oif=${rule.outgoing_iface ? interfaceName(rule.outgoing_iface) : "*"}</td>
                <td>${HF.escapeHtml(mark)}</td>
                <td>${HF.escapeHtml(rule.action)}</td>
                <td><span class="status ${status.className}">${status.label}</span>${protectedBadge(rule)}</td>
                <td>
                    <button class="text-button compact" type="button" data-policy-toggle data-kind="routing_rules"
                        data-id="${HF.escapeHtml(rule.id)}" data-enabled="${nextEnabled}" ${toggleDisabled}>${buttonLabel}</button>
                    <button class="text-button compact danger" type="button" data-policy-delete data-kind="routing_rules"
                        data-id="${HF.escapeHtml(rule.id)}" ${deleteDisabled}>Delete</button>
                </td>
            </tr>
        `;
    }

    function tableRow(table) {
        const status = itemStatus(table);
        const pending = numberValue(table.pending_delete) === 1;
        const protectedItem = policyItemProtected(table);
        const enabled = numberValue(table.enabled) === 1;
        const toggleDisabled = pending || (enabled && protectedItem) ? "disabled" : "";
        const deleteDisabled = pending || protectedItem || !enabled ? "disabled" : "";
        const nextEnabled = enabled ? 0 : 1;
        const buttonLabel = enabled ? "Disable" : "Enable";
        return `
            <tr>
                <td>${HF.escapeHtml(table.table_id)}</td>
                <td><strong>${HF.escapeHtml(table.table_name)}</strong></td>
                <td>${HF.escapeHtml(table.description || "-")}</td>
                <td><span class="status ${status.className}">${status.label}</span>${protectedBadge(table)}</td>
                <td>
                    <button class="text-button compact" type="button" data-policy-toggle data-kind="routing_tables"
                        data-id="${HF.escapeHtml(table.id)}" data-enabled="${nextEnabled}" ${toggleDisabled}>${buttonLabel}</button>
                    <button class="text-button compact danger" type="button" data-policy-delete data-kind="routing_tables"
                        data-id="${HF.escapeHtml(table.id)}" ${deleteDisabled}>Delete</button>
                </td>
            </tr>
        `;
    }

    function renderData(data) {
        currentData = data;
        refreshTableChoices();
        refreshRouteTableFilter();
        refreshRuleTableFilter();
        const routes = filteredRoutes();
        const rules = filteredRules();
        const pagedRoutes = pagedItems("routes", routes);
        const pagedRules = pagedItems("rules", rules);
        const pagedTables = pagedItems("tables", data.tables || []);
        setMetric("#policy-summary-tables", data.summary.tables);
        setMetric("#policy-summary-routes", data.summary.routes);
        setMetric("#policy-summary-rules", data.summary.rules);
        setMetric("#policy-summary-enabled", data.summary.enabled);
        document.querySelector("#policy-routes-count").textContent = `${familyLabel(activeFamily)} routes=${routes.length}`;
        document.querySelector("#policy-rules-count").textContent = `${familyLabel(activeRuleFamily)} rules=${rules.length}`;
        document.querySelector("#policy-tables-count").textContent = `tables=${data.tables.length}`;
        routesBody.innerHTML = routes.length ? pagedRoutes.map(routeRow).join("") : emptyRow(9, `no ${familyLabel(activeFamily)} policy routes`);
        rulesBody.innerHTML = rules.length ? pagedRules.map(ruleRow).join("") : emptyRow(7, `no ${familyLabel(activeRuleFamily)} policy rules`);
        tablesBody.innerHTML = data.tables.length ? pagedTables.map(tableRow).join("") : emptyRow(5, "no routing tables");
        setPolicyFormFamily();
    }

    function emptyRow(colspan, message) {
        return `<tr><td colspan="${colspan}"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(message)}</span></div></td></tr>`;
    }

    function renderWorkRequests(data) {
        const requests = data.requests || [];
        workRequestsCount.textContent = `requests=${requests.length}`;
        workRequestsBody.innerHTML = requests.length ? requests.map((request) => {
            const failed = request.status === "failed";
            return `
                <tr>
                    <td>${HF.escapeHtml(request.id)}</td>
                    <td><span class="status ${failed ? "down" : "up"}">${HF.escapeHtml(request.status)}</span></td>
                    <td>${HF.escapeHtml(request.category_name)}</td>
                    <td>${HF.escapeHtml(request.action_name)}</td>
                    <td>${HF.escapeHtml(request.updated_at)}</td>
                    <td>${HF.escapeHtml(request.error_message)}</td>
                </tr>
            `;
        }).join("") : emptyRow(6, "no policy routing work requests");
    }

    async function loadData() {
        try {
            setState("Loading");
            const data = await HF.fetchJson("/api/network/policy-routing");
            renderData(data);
            setState("Ready");
        } catch (error) {
            setState("Offline");
            routesBody.innerHTML = emptyRow(10, error.message);
        }
    }

    async function loadWorkRequests() {
        if (workRequestsLoading) {
            return;
        }
        workRequestsLoading = true;
        try {
            const data = await HF.fetchJson("/api/network/policy-routing/work-requests");
            renderWorkRequests(data);
        } catch (error) {
            workRequestsBody.innerHTML = emptyRow(6, error.message);
        } finally {
            workRequestsLoading = false;
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

    function createContextForTab(tabName) {
        if (tabName === "new-route") {
            return "routes";
        }
        if (tabName === "new-rule") {
            return "rules";
        }
        if (tabName === "new-table") {
            return "tables";
        }
        return tabName;
    }

    function setActiveTab(tabName, refreshData = false) {
        const createContext = createContextForTab(tabName);
        document.querySelectorAll("[data-policy-tab]").forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.policyTab === tabName);
        });
        document.querySelectorAll("[data-policy-view]").forEach((view) => {
            view.hidden = view.dataset.policyView !== tabName;
        });
        createButtons.forEach((button) => {
            button.hidden = button.dataset.policyCreateFor !== createContext;
        });
        if (tabName !== "work-requests") {
            stopWorkRequestsPolling();
        }
        if (!refreshData) {
            return;
        }
        if (tabName === "work-requests") {
            startWorkRequestsPolling();
        } else {
            loadData();
        }
    }

    function payloadFromForm(form) {
        return Object.fromEntries(new FormData(form).entries());
    }

    async function submitForm(event, form, url, statusElement) {
        event.preventDefault();
        try {
            setStatus(statusElement, "queue=writing");
            const result = await HF.fetchJson(url, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payloadFromForm(form)),
            });
            setStatus(statusElement, `saved=${result.route_id || result.rule_id || result.table_row_id}`);
            form.reset();
            updateRuleFormShape();
            setPolicyFormFamily();
            setActiveTab(url.includes("routes") ? "routes" : url.includes("rules") ? "rules" : "tables", true);
        } catch (error) {
            setStatus(statusElement, `error=${error.message}`);
        }
    }

    async function toggleItem(button) {
        try {
            button.disabled = true;
            const result = await HF.fetchJson(`/api/network/policy-routing/${button.dataset.kind}/${button.dataset.id}/enabled`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({enabled: Number(button.dataset.enabled)}),
            });
            setState(`saved=${result.item_id}`);
            await loadData();
        } catch (error) {
            setState(`error=${error.message}`);
            button.disabled = false;
        }
    }

    function openDeleteModal(button) {
        pendingDelete = button;
        const label = `${button.dataset.kind}/${button.dataset.id}`;
        deleteItemLabel.textContent = `item=${label}`;
        deleteMessage.textContent = `Are you sure you want to delete ${label}?`;
        deleteModal.hidden = false;
    }

    function closeDeleteModal() {
        pendingDelete = null;
        deleteModal.hidden = true;
    }

    async function deleteItem() {
        if (!pendingDelete) {
            return;
        }
        const button = pendingDelete;
        try {
            deleteConfirmButton.disabled = true;
            const result = await HF.fetchJson(`/api/network/policy-routing/${button.dataset.kind}/${button.dataset.id}`, {
                method: "DELETE",
            });
            setState(`saved=${result.item_id}`);
            closeDeleteModal();
            await loadData();
        } catch (error) {
            setState(`error=${error.message}`);
        } finally {
            deleteConfirmButton.disabled = false;
        }
    }

    function openApplyModal() {
        applyModal.hidden = false;
    }

    function closeApplyModal() {
        applyModal.hidden = true;
    }

    async function applyPolicyRouting() {
        try {
            applyConfirmButton.disabled = true;
            const result = await HF.fetchJson("/api/network/policy-routing/apply", {method: "POST"});
            setState(`queued=${result.work_request_count}`);
            closeApplyModal();
            setActiveTab("work-requests", true);
        } catch (error) {
            setState(`error=${error.message}`);
        } finally {
            applyConfirmButton.disabled = false;
        }
    }

    document.querySelectorAll("[data-policy-tab]").forEach((tab) => {
        tab.addEventListener("click", () => setActiveTab(tab.dataset.policyTab, true));
    });
    familyButtons.forEach((button) => {
        button.addEventListener("click", () => setActiveFamily(button.dataset.policyFamily));
    });
    if (familyFilterSelect) {
        familyFilterSelect.addEventListener("change", () => setActiveFamily(familyFilterSelect.value));
    }
    if (tableFilterSelect) {
        tableFilterSelect.addEventListener("change", () => setActiveRouteTable(tableFilterSelect.value));
    }
    if (ruleFamilyFilterSelect) {
        ruleFamilyFilterSelect.addEventListener("change", () => setActiveRuleFamily(ruleFamilyFilterSelect.value));
    }
    if (ruleTableFilterSelect) {
        ruleTableFilterSelect.addEventListener("change", () => setActiveRuleTable(ruleTableFilterSelect.value));
    }
    Object.entries(pageSizeSelects).forEach(([kind, select]) => {
        if (!select) {
            return;
        }
        select.addEventListener("change", () => {
            viewPagination[kind].page = 1;
            viewPagination[kind].pageSize = Number(select.value) || 25;
            renderData(currentData);
        });
    });
    Object.entries(pagePrevButtons).forEach(([kind, button]) => {
        if (!button) {
            return;
        }
        button.addEventListener("click", () => {
            viewPagination[kind].page = Math.max(1, viewPagination[kind].page - 1);
            renderData(currentData);
        });
    });
    Object.entries(pageNextButtons).forEach(([kind, button]) => {
        if (!button) {
            return;
        }
        button.addEventListener("click", () => {
            viewPagination[kind].page += 1;
            renderData(currentData);
        });
    });
    document.querySelectorAll("[data-policy-apply]").forEach((button) => {
        button.addEventListener("click", openApplyModal);
    });
    document.querySelectorAll("[data-apply-cancel]").forEach((button) => {
        button.addEventListener("click", closeApplyModal);
    });
    document.querySelectorAll("[data-delete-cancel]").forEach((button) => {
        button.addEventListener("click", closeDeleteModal);
    });
    applyConfirmButton.addEventListener("click", applyPolicyRouting);
    deleteConfirmButton.addEventListener("click", deleteItem);
    ruleActionSelect.addEventListener("change", updateRuleFormShape);
    routeFamilySelect.addEventListener("change", () => setActiveFamily(routeFamilySelect.value));
    ruleFamilySelect.addEventListener("change", () => setActiveRuleFamily(ruleFamilySelect.value));
    routeForm.addEventListener("submit", (event) => submitForm(event, routeForm, "/api/network/policy-routing/routes", routeStatus));
    ruleForm.addEventListener("submit", (event) => submitForm(event, ruleForm, "/api/network/policy-routing/rules", ruleStatus));
    tableForm.addEventListener("submit", (event) => submitForm(event, tableForm, "/api/network/policy-routing/tables", tableStatus));
    document.querySelectorAll("[data-policy-view]").forEach((view) => {
        view.addEventListener("click", (event) => {
            const toggleButton = event.target.closest("[data-policy-toggle]");
            const deleteButton = event.target.closest("[data-policy-delete]");
            if (toggleButton) {
                toggleItem(toggleButton);
                return;
            }
            if (deleteButton) {
                openDeleteModal(deleteButton);
            }
        });
    });

    updateRuleFormShape();
    setActiveFamily("ipv4");
    setActiveTab("routes");
    loadInterfaceChoices();
    loadData();
}());
