(function () {
    const stateLabel = document.querySelector("#dnsmasq-state");
    const form = document.querySelector("#dnsmasq-form");
    const statusLabel = document.querySelector("#dnsmasq-form-status");
    const applyButton = document.querySelector("#dnsmasq-apply");
    const interfacePicker = document.querySelector("#dnsmasq-interface-picker");
    const interfaceAddButton = document.querySelector("#dnsmasq-interface-add");
    const activeInterfacesBody = document.querySelector("#dnsmasq-active-interfaces");
    const dnsScopeList = document.querySelector("#dnsmasq-dns-scope-list");
    const dhcpScopeList = document.querySelector("#dnsmasq-dhcp-scope-list");
    const forwardedDomainsEnabled = document.querySelector("#dnsmasq-forwarded-domains-enabled");
    const forwardedDomainControls = Array.from(document.querySelectorAll(".dnsmasq-forwarded-domain-control"));
    const domainUpstreamDomain = document.querySelector("#dnsmasq-domain-upstream-domain");
    const domainUpstreamServers = document.querySelector("#dnsmasq-domain-upstream-servers");
    const domainUpstreamBody = document.querySelector("#dnsmasq-domain-upstreams");
    const actionModal = document.querySelector("#dnsmasq-action-modal");
    const actionTitle = document.querySelector("#dnsmasq-action-title");
    const actionMessage = document.querySelector("#dnsmasq-action-message");
    const actionConfirm = document.querySelector("[data-dnsmasq-modal-confirm]");
    const tabButtons = Array.from(document.querySelectorAll("[data-dnsmasq-tab]"));
    const tabPanels = Array.from(document.querySelectorAll("[data-dnsmasq-panel]"));
    const tabNav = document.querySelector(".dnsmasq-tabs");
    const POLL_MS = 8000;
    const ALL_INTERFACES = "__all__";
    const ALL_INTERFACES_LABEL = "Global configuration applied to all interfaces";
    let loading = false;
    let dirty = false;
    let pendingAction = null;
    let currentServiceState = "";
    let availableInterfaces = [];
    let activeInterfaces = [];
    let domainUpstreams = [];
    let interfaceConfigs = [];
    let currentConfig = {};

    function setDirty(value) {
        dirty = Boolean(value);
        if (applyButton) {
            applyButton.hidden = !dirty;
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

    function setText(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            element.textContent = HF.text(value);
        }
    }

    function setValue(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            element.value = HF.text(value);
        }
    }

    function setBoolean(selector, value) {
        setValue(selector, value ? "1" : "0");
    }

    function setChecked(selector, value) {
        const element = document.querySelector(selector);
        if (element) {
            element.checked = Boolean(value);
        }
    }

    function booleanValue(selector) {
        const element = document.querySelector(selector);
        return element ? element.value === "1" : false;
    }

    function checkedValue(selector) {
        const element = document.querySelector(selector);
        return element ? element.checked : false;
    }

    function syncPiholeUpstreamState() {
        const upstream = document.querySelector("#dnsmasq-upstream-dns");
        const enabled = checkedValue("#dnsmasq-pihole-upstream");
        if (upstream) {
            upstream.disabled = enabled;
            upstream.classList.toggle("is-disabled", enabled);
        }
        if (forwardedDomainsEnabled) {
            forwardedDomainsEnabled.disabled = enabled;
            if (enabled) {
                forwardedDomainsEnabled.checked = false;
            }
        }
        syncForwardedDomainState();
    }

    function forwardedDomainsAreEnabled() {
        return forwardedDomainsEnabled ? forwardedDomainsEnabled.checked && !forwardedDomainsEnabled.disabled : false;
    }

    function syncForwardedDomainState() {
        const enabled = forwardedDomainsAreEnabled();
        forwardedDomainControls.forEach((element) => {
            element.hidden = !enabled;
        });
    }

    function textareaLines(selector) {
        const element = document.querySelector(selector);
        if (!element) {
            return [];
        }
        return element.value
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean);
    }

    function splitServerTokens(value) {
        return HF.text(value)
            .split(/[\s,]+/)
            .map((item) => item.trim())
            .filter(Boolean);
    }

    function selectedInterfaces() {
        return [...activeInterfaces];
    }

    function showTab(tabName) {
        if (!activeInterfaces.length) {
            tabButtons.forEach((button) => {
                button.classList.remove("active");
            });
            tabPanels.forEach((panel) => {
                panel.hidden = true;
            });
            if (tabNav) {
                tabNav.hidden = true;
            }
            return;
        }
        if (tabNav) {
            tabNav.hidden = false;
        }
        tabButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.dnsmasqTab === tabName);
        });
        tabPanels.forEach((panel) => {
            panel.hidden = panel.dataset.dnsmasqPanel !== tabName;
        });
    }

    function interfaceMeta(name) {
        if (name === ALL_INTERFACES) {
            return {name, role: "GLOBAL", description: ALL_INTERFACES_LABEL};
        }
        return availableInterfaces.find((iface) => iface.name === name) || {name, role: "-", description: "-"};
    }

    function interfaceDisplayName(name) {
        if (name === ALL_INTERFACES) {
            return ALL_INTERFACES_LABEL;
        }
        const iface = interfaceMeta(name);
        const role = iface.role || "UNKNOWN";
        const description = iface.description || "-";
        return `${name} (${role}) - ${description}`;
    }

    function activeInterfaceNames() {
        if (activeInterfaces.includes(ALL_INTERFACES)) {
            return [ALL_INTERFACES];
        }
        return [...activeInterfaces];
    }

    function formatEnabled(value) {
        return value ? "enabled" : "disabled";
    }

    function renderConfigItem(label, value) {
        return `
            <div class="dnsmasq-scope-item">
                <span>${HF.escapeHtml(label)}</span>
                <strong>${HF.escapeHtml(HF.text(value || "-"))}</strong>
            </div>
        `;
    }

    function fieldValue(value, fallback = "") {
        return HF.escapeHtml(HF.text(value ?? fallback));
    }

    function checkedAttr(value) {
        return value ? " checked" : "";
    }

    function selectedAttr(value, expected) {
        return value === expected ? " selected" : "";
    }

    function configForInterface(name) {
        return interfaceConfigs.find((item) => item.iface === name) || buildInterfaceConfig(name);
    }

    function buildInterfaceConfig(name) {
        return {
            iface: name,
            dns_enabled: Boolean(currentConfig.dns_enabled),
            local_domain: currentConfig.local_domain || "armfirewall.local",
            upstream_dns_servers: [...(currentConfig.upstream_dns_servers || ["1.1.1.1", "8.8.8.8"])],
            domain_upstreams: (currentConfig.domain_upstreams || []).map((item) => ({domain: item.domain, upstreams: [...(item.upstreams || [])]})),
            pihole_upstream_enabled: Boolean(currentConfig.pihole_upstream_enabled),
            cache_size: currentConfig.cache_size || 1000,
            expand_hosts: currentConfig.expand_hosts !== false,
            domain_needed: currentConfig.domain_needed !== false,
            bogus_priv: currentConfig.bogus_priv !== false,
            dhcp_enabled: Boolean(currentConfig.dhcp_enabled),
            dhcp_range_start: currentConfig.dhcp_range_start || "",
            dhcp_range_end: currentConfig.dhcp_range_end || "",
            lease_time: currentConfig.lease_time || "12h",
            dhcp_authoritative: Boolean(currentConfig.dhcp_authoritative),
        };
    }

    function syncInterfaceConfigs() {
        const names = activeInterfaceNames();
        const incoming = currentConfig.interface_configs || [];
        interfaceConfigs = names.map((name) => {
            const existing = interfaceConfigs.find((item) => item.iface === name);
            const saved = incoming.find((item) => item.iface === name);
            return existing || saved || buildInterfaceConfig(name);
        });
        domainUpstreams = interfaceConfigs[0]?.domain_upstreams || [];
    }

    function updateInterfaceConfig(name, field, value) {
        const config = configForInterface(name);
        config[field] = value;
        if (field === "pihole_upstream_enabled" && value) {
            config.domain_upstreams = [];
        }
        interfaceConfigs = interfaceConfigs.filter((item) => item.iface !== name).concat(config);
        domainUpstreams = config.domain_upstreams || [];
    }

    function renderDomainRowsForConfig(config) {
        const rows = config.domain_upstreams || [];
        if (!rows.length) {
            return `<tr><td colspan="3"><div class="terminal-empty"><span class="prompt">$</span><span>no forwarded domains</span></div></td></tr>`;
        }
        return rows.map((item, index) => `
            <tr>
                <td><strong>${HF.escapeHtml(item.domain)}</strong></td>
                <td>${HF.escapeHtml((item.upstreams || []).join(", "))}</td>
                <td><button class="text-button compact danger" type="button" data-dnsmasq-scope-domain-remove="${index}">Remove</button></td>
            </tr>
        `).join("");
    }

    function renderDnsScopeCards() {
        if (!dnsScopeList) {
            return;
        }
        const names = activeInterfaceNames();
        if (!names.length) {
            dnsScopeList.innerHTML = "";
            return;
        }
        dnsScopeList.innerHTML = names.map((name) => {
            const iface = interfaceMeta(name);
            const displayName = interfaceDisplayName(name);
            const config = configForInterface(name);
            const forwardedEnabled = !config.pihole_upstream_enabled && (config.domain_upstreams || []).length > 0;
            return `
                <section class="dnsmasq-scope-card" data-dnsmasq-scope="dns" data-iface="${HF.escapeHtml(name)}">
                    <div class="dnsmasq-scope-head">
                        <strong>DNS configuration</strong>
                        <span><b>${HF.escapeHtml(displayName)}</b> / ${HF.escapeHtml(iface.role || "GLOBAL")} / ${HF.escapeHtml(iface.description || "-")}</span>
                    </div>
                    <div class="form-grid dnsmasq-scope-form">
                        <label class="field">
                            <span>DNS enabled</span>
                            <select data-scope-field="dns_enabled">
                                <option value="1"${selectedAttr(config.dns_enabled ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.dns_enabled ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>LAN local domain</span>
                            <input data-scope-field="local_domain" type="text" autocomplete="off" value="${fieldValue(config.local_domain, "armfirewall.local")}">
                        </label>
                        <label class="field">
                            <span>Cache size</span>
                            <input data-scope-field="cache_size" type="number" min="0" max="1000000" value="${fieldValue(config.cache_size, 1000)}">
                        </label>
                        <label class="field">
                            <span>Expand hosts</span>
                            <select data-scope-field="expand_hosts">
                                <option value="1"${selectedAttr(config.expand_hosts ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.expand_hosts ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>Domain needed</span>
                            <select data-scope-field="domain_needed">
                                <option value="1"${selectedAttr(config.domain_needed ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.domain_needed ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>Bogus priv</span>
                            <select data-scope-field="bogus_priv">
                                <option value="1"${selectedAttr(config.bogus_priv ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.bogus_priv ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field wide">
                            <span>Default upstream DNS servers</span>
                            <textarea data-scope-field="upstream_dns_servers" rows="3" spellcheck="false"${config.pihole_upstream_enabled ? " disabled" : ""}>${fieldValue((config.upstream_dns_servers || []).join("\n"))}</textarea>
                        </label>
                        <label class="check-line wide">
                            <input data-scope-field="pihole_upstream_enabled" type="checkbox"${checkedAttr(config.pihole_upstream_enabled)}>
                            <span>Enable piHole DNS Upstream?</span>
                        </label>
                        <label class="check-line wide">
                            <input data-scope-field="forwarded_domains_enabled" type="checkbox"${checkedAttr(forwardedEnabled)}${config.pihole_upstream_enabled ? " disabled" : ""}>
                            <span>Enable forwarded domains?</span>
                        </label>
                        <label class="field dnsmasq-forwarded-domain-row"${forwardedEnabled ? "" : " hidden"}>
                            <span>Forwarded domain</span>
                            <input data-dnsmasq-scope-domain type="text" autocomplete="off" placeholder="empresa.local">
                        </label>
                        <label class="field dnsmasq-domain-upstream-servers dnsmasq-forwarded-domain-row"${forwardedEnabled ? "" : " hidden"}>
                            <span>Forward to DNS servers</span>
                            <textarea data-dnsmasq-scope-servers rows="2" spellcheck="false" placeholder="192.168.10.10 192.168.10.11"></textarea>
                        </label>
                        <div class="field dnsmasq-domain-upstream-action dnsmasq-forwarded-domain-row"${forwardedEnabled ? "" : " hidden"}>
                            <span>Action</span>
                            <button class="icon-button" type="button" data-dnsmasq-scope-domain-add title="Add domain upstream" aria-label="Add domain upstream">+</button>
                        </div>
                        <div class="table-wrap wide dnsmasq-domain-upstream-scroll dnsmasq-forwarded-domain-row"${forwardedEnabled ? "" : " hidden"}>
                            <table class="data-table dnsmasq-domain-upstream-table">
                                <thead><tr><th>Domain</th><th>Upstreams</th><th>Action</th></tr></thead>
                                <tbody>${renderDomainRowsForConfig(config)}</tbody>
                            </table>
                        </div>
                    </div>
                </section>
            `;
        }).join("");
    }

    function renderDhcpScopeCards() {
        if (!dhcpScopeList) {
            return;
        }
        const names = activeInterfaceNames();
        if (!names.length) {
            dhcpScopeList.innerHTML = "";
            return;
        }
        dhcpScopeList.innerHTML = names.map((name) => {
            const iface = interfaceMeta(name);
            const displayName = interfaceDisplayName(name);
            const config = configForInterface(name);
            return `
                <section class="dnsmasq-scope-card" data-dnsmasq-scope="dhcp" data-iface="${HF.escapeHtml(name)}">
                    <div class="dnsmasq-scope-head">
                        <strong>DHCP configuration</strong>
                        <span><b>${HF.escapeHtml(displayName)}</b> / ${HF.escapeHtml(iface.role || "GLOBAL")} / ${HF.escapeHtml(iface.description || "-")}</span>
                    </div>
                    <div class="form-grid dnsmasq-scope-form">
                        <label class="field">
                            <span>DHCP enabled</span>
                            <select data-scope-field="dhcp_enabled">
                                <option value="1"${selectedAttr(config.dhcp_enabled ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.dhcp_enabled ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>DHCP range start</span>
                            <input data-scope-field="dhcp_range_start" type="text" autocomplete="off" value="${fieldValue(config.dhcp_range_start)}">
                        </label>
                        <label class="field">
                            <span>DHCP range end</span>
                            <input data-scope-field="dhcp_range_end" type="text" autocomplete="off" value="${fieldValue(config.dhcp_range_end)}">
                        </label>
                        <label class="field">
                            <span>Lease time</span>
                            <input data-scope-field="lease_time" type="text" autocomplete="off" value="${fieldValue(config.lease_time, "12h")}">
                        </label>
                        <label class="field">
                            <span>DHCP authoritative</span>
                            <select data-scope-field="dhcp_authoritative">
                                <option value="1"${selectedAttr(config.dhcp_authoritative ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.dhcp_authoritative ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                    </div>
                </section>
            `;
        }).join("");
    }

    function renderScopeCards() {
        renderDnsScopeCards();
        renderDhcpScopeCards();
    }

    function renderInterfacePicker() {
        if (!interfacePicker) {
            return;
        }
        const activeSet = new Set(activeInterfaces);
        const hasAllInterfaces = activeSet.has(ALL_INTERFACES);
        const options = hasAllInterfaces ? [] : [
            ...(activeSet.size === 0 ? [{name: ALL_INTERFACES, role: "GLOBAL", description: ALL_INTERFACES_LABEL}] : []),
            ...availableInterfaces.filter((iface) => !activeSet.has(iface.name)),
        ];
        interfacePicker.innerHTML = options.length
            ? options.map((iface) => {
                if (iface.name === ALL_INTERFACES) {
                    return `<option value="${HF.escapeHtml(iface.name)}">${HF.escapeHtml(iface.description)}</option>`;
                }
                const role = HF.text(iface.role || "UNKNOWN");
                const description = HF.text(iface.description || "-");
                const label = `${HF.text(iface.name)} (${role}) - ${description}`;
                return `<option value="${HF.escapeHtml(iface.name)}">${HF.escapeHtml(label)}</option>`;
            }).join("")
            : '<option value="">no interfaces available</option>';
        if (interfaceAddButton) {
            interfaceAddButton.disabled = !options.length;
        }
    }

    function renderActiveInterfaces() {
        if (!activeInterfacesBody) {
            return;
        }
        if (!activeInterfaces.length) {
            activeInterfacesBody.innerHTML = `
                <tr>
                    <td colspan="4"><div class="terminal-empty"><span class="prompt">$</span><span>no active interfaces</span></div></td>
                </tr>
            `;
            renderScopeCards();
            showTab("dns");
            return;
        }
        activeInterfacesBody.innerHTML = activeInterfaces.map((name) => {
            const iface = interfaceMeta(name);
            if (name === ALL_INTERFACES) {
                return `
                    <tr>
                        <td colspan="3"><strong>${HF.escapeHtml(iface.description)}</strong></td>
                        <td><button class="text-button compact danger" type="button" data-dnsmasq-interface-remove="${HF.escapeHtml(name)}">Remove</button></td>
                    </tr>
                `;
            }
            const displayName = interfaceDisplayName(name);
            return `
                <tr>
                    <td><strong>${HF.escapeHtml(displayName)}</strong></td>
                    <td>${HF.escapeHtml(iface.role || "-")}</td>
                    <td>${HF.escapeHtml(iface.description || "-")}</td>
                    <td><button class="text-button compact danger" type="button" data-dnsmasq-interface-remove="${HF.escapeHtml(name)}">Remove</button></td>
                </tr>
            `;
        }).join("");
        renderScopeCards();
        if (!tabButtons.some((button) => button.classList.contains("active"))) {
            showTab("dns");
        } else {
            const activeButton = tabButtons.find((button) => button.classList.contains("active"));
            showTab(activeButton?.dataset.dnsmasqTab || "dns");
        }
    }

    function renderInterfaces(interfaces, selected) {
        availableInterfaces = interfaces || [];
        const selectedSet = new Set(selected || []);
        if (selectedSet.has(ALL_INTERFACES)) {
            activeInterfaces = [ALL_INTERFACES];
        } else {
            activeInterfaces = availableInterfaces
                .filter((iface) => selectedSet.has(iface.name))
                .map((iface) => iface.name);
            for (const name of selected || []) {
                if (!activeInterfaces.includes(name)) {
                    activeInterfaces.push(name);
                }
            }
        }
        syncInterfaceConfigs();
        renderInterfacePicker();
        renderActiveInterfaces();
    }

    function addSelectedInterface() {
        if (!interfacePicker || !interfacePicker.value) {
            return;
        }
        if (!activeInterfaces.includes(interfacePicker.value)) {
            activeInterfaces = interfacePicker.value === ALL_INTERFACES ? [ALL_INTERFACES] : activeInterfaces.filter((name) => name !== ALL_INTERFACES).concat(interfacePicker.value);
            syncInterfaceConfigs();
            setDirty(true);
            renderInterfacePicker();
            renderActiveInterfaces();
            renderScopeCards();
            setText("#dnsmasq-summary-interfaces", activeInterfaces.length);
        }
    }

    function removeInterface(name) {
        activeInterfaces = activeInterfaces.filter((item) => item !== name);
        syncInterfaceConfigs();
        setDirty(true);
        renderInterfacePicker();
        renderActiveInterfaces();
        renderScopeCards();
        setText("#dnsmasq-summary-interfaces", activeInterfaces.length);
    }

    function renderDomainUpstreams(items) {
        domainUpstreams = (items || []).map((item) => ({
            domain: HF.text(item.domain).trim(),
            upstreams: Array.isArray(item.upstreams) ? item.upstreams.map((server) => HF.text(server).trim()).filter(Boolean) : splitServerTokens(item.upstreams),
        })).filter((item) => item.domain && item.upstreams.length);
        if (!domainUpstreamBody) {
            return;
        }
        if (forwardedDomainsEnabled) {
            forwardedDomainsEnabled.checked = Boolean(domainUpstreams.length);
        }
        syncForwardedDomainState();
        if (!domainUpstreams.length) {
            domainUpstreamBody.innerHTML = `
                <tr>
                    <td colspan="3"><div class="terminal-empty"><span class="prompt">$</span><span>no domain upstreams</span></div></td>
                </tr>
            `;
            renderScopeCards();
            return;
        }
        domainUpstreamBody.innerHTML = domainUpstreams.map((item, index) => `
            <tr>
                <td><strong>${HF.escapeHtml(item.domain)}</strong></td>
                <td>${HF.escapeHtml(item.upstreams.join(", "))}</td>
                <td><button class="text-button compact danger" type="button" data-dnsmasq-domain-upstream-remove="${index}">Remove</button></td>
            </tr>
        `).join("");
        renderScopeCards();
    }

    function addDomainUpstream() {
        if (!forwardedDomainsAreEnabled()) {
            return;
        }
        const domain = HF.text(domainUpstreamDomain?.value).trim().replace(/\.$/, "");
        const upstreams = splitServerTokens(domainUpstreamServers?.value || "");
        if (!domain || !upstreams.length) {
            if (statusLabel) {
                statusLabel.textContent = "domain and upstream servers are required";
            }
            return;
        }
        const existing = domainUpstreams.find((item) => item.domain === domain);
        if (existing) {
            upstreams.forEach((server) => {
                if (!existing.upstreams.includes(server)) {
                    existing.upstreams.push(server);
                }
            });
        } else {
            domainUpstreams.push({domain, upstreams});
        }
        if (domainUpstreamDomain) {
            domainUpstreamDomain.value = "";
        }
        if (domainUpstreamServers) {
            domainUpstreamServers.value = "";
        }
        setDirty(true);
        renderDomainUpstreams(domainUpstreams);
    }

    function removeDomainUpstream(index) {
        domainUpstreams.splice(index, 1);
        setDirty(true);
        renderDomainUpstreams(domainUpstreams);
    }

    function addScopeDomainUpstream(button) {
        const card = button.closest("[data-iface]");
        if (!card) {
            return;
        }
        const iface = card.dataset.iface;
        const domainInput = card.querySelector("[data-dnsmasq-scope-domain]");
        const serversInput = card.querySelector("[data-dnsmasq-scope-servers]");
        const domain = HF.text(domainInput?.value).trim().replace(/\.$/, "");
        const upstreams = splitServerTokens(serversInput?.value || "");
        if (!domain || !upstreams.length) {
            if (statusLabel) {
                statusLabel.textContent = "domain and upstream servers are required";
            }
            return;
        }
        const config = configForInterface(iface);
        const existing = (config.domain_upstreams || []).find((item) => item.domain === domain);
        if (existing) {
            upstreams.forEach((server) => {
                if (!existing.upstreams.includes(server)) {
                    existing.upstreams.push(server);
                }
            });
        } else {
            config.domain_upstreams = (config.domain_upstreams || []).concat({domain, upstreams});
        }
        updateInterfaceConfig(iface, "domain_upstreams", config.domain_upstreams);
        setDirty(true);
        renderScopeCards();
    }

    function removeScopeDomainUpstream(button) {
        const card = button.closest("[data-iface]");
        if (!card) {
            return;
        }
        const iface = card.dataset.iface;
        const config = configForInterface(iface);
        config.domain_upstreams = (config.domain_upstreams || []).filter((_, index) => index !== Number(button.dataset.dnsmasqScopeDomainRemove));
        updateInterfaceConfig(iface, "domain_upstreams", config.domain_upstreams);
        setDirty(true);
        renderScopeCards();
    }

    function renderConfig(data) {
        const config = data.config || {};
        currentConfig = config;
        const summary = data.summary || {};
        const service = data.service || {};
        currentServiceState = String(service.state || "").toUpperCase();
        renderInterfaces(data.interfaces || [], config.listen_interfaces || []);

        setBoolean("#dnsmasq-dns-enabled", config.dns_enabled);
        setBoolean("#dnsmasq-dhcp-enabled", config.dhcp_enabled);
        setValue("#dnsmasq-local-domain", config.local_domain);
        setValue("#dnsmasq-cache-size", config.cache_size);
        setValue("#dnsmasq-upstream-dns", (config.upstream_dns_servers || []).join("\n"));
        renderDomainUpstreams(config.domain_upstreams || []);
        setChecked("#dnsmasq-pihole-upstream", config.pihole_upstream_enabled);
        syncPiholeUpstreamState();
        setValue("#dnsmasq-dhcp-start", config.dhcp_range_start);
        setValue("#dnsmasq-dhcp-end", config.dhcp_range_end);
        setValue("#dnsmasq-lease-time", config.lease_time);
        setBoolean("#dnsmasq-expand-hosts", config.expand_hosts);
        setBoolean("#dnsmasq-domain-needed", config.domain_needed);
        setBoolean("#dnsmasq-bogus-priv", config.bogus_priv);
        setBoolean("#dnsmasq-dhcp-authoritative", config.dhcp_authoritative);
        setValue("#dnsmasq-extra-options", config.extra_options);

        setText("#dnsmasq-summary-service", service.state || "-");
        setText("#dnsmasq-summary-dns", config.dns_enabled ? "enabled" : "disabled");
        setText("#dnsmasq-summary-dhcp", config.dhcp_enabled ? "enabled" : "disabled");
        setText("#dnsmasq-summary-interfaces", (config.listen_interfaces || []).length);
        setText("#dnsmasq-summary-version", service.version || "-");
        setText("#dnsmasq-summary-pid", service.pid || "-");
        setText("#dnsmasq-summary-uptime", service.uptime || "-");
        setText("#dnsmasq-config-path", `config=${summary.config_path || "-"}`);
        setState("Live", summary.updated_at || "-");
    }

    function formPayload() {
        const firstConfig = interfaceConfigs[0] || buildInterfaceConfig("");
        return {
            dns_enabled: interfaceConfigs.some((item) => item.dns_enabled),
            dhcp_enabled: interfaceConfigs.some((item) => item.dhcp_enabled),
            listen_interfaces: selectedInterfaces(),
            interface_configs: interfaceConfigs,
            local_domain: firstConfig.local_domain || "",
            upstream_dns_servers: firstConfig.upstream_dns_servers || [],
            domain_upstreams: firstConfig.domain_upstreams || [],
            pihole_upstream_enabled: Boolean(firstConfig.pihole_upstream_enabled),
            dhcp_range_start: firstConfig.dhcp_range_start || "",
            dhcp_range_end: firstConfig.dhcp_range_end || "",
            lease_time: firstConfig.lease_time || "",
            cache_size: firstConfig.cache_size || 0,
            expand_hosts: Boolean(firstConfig.expand_hosts),
            domain_needed: Boolean(firstConfig.domain_needed),
            bogus_priv: Boolean(firstConfig.bogus_priv),
            dhcp_authoritative: Boolean(firstConfig.dhcp_authoritative),
            extra_options: document.querySelector("#dnsmasq-extra-options")?.value || "",
        };
    }

    function syncCurrentConfigFromForm() {
        currentConfig = {...currentConfig, ...formPayload()};
    }

    function scopeFieldValue(element, field) {
        if (element.type === "checkbox") {
            return element.checked;
        }
        if (element.tagName === "SELECT") {
            return element.value === "1";
        }
        if (field === "upstream_dns_servers") {
            return textareaLinesFromElement(element);
        }
        if (field === "cache_size") {
            return element.value || 0;
        }
        return element.value.trim();
    }

    function textareaLinesFromElement(element) {
        return element.value
            .split(/\r?\n/)
            .map((line) => line.trim())
            .filter(Boolean);
    }

    function handleScopeFieldChange(element) {
        const card = element.closest("[data-iface]");
        if (!card) {
            return false;
        }
        const iface = card.dataset.iface;
        const field = element.dataset.scopeField;
        if (!field) {
            return false;
        }
        if (field === "forwarded_domains_enabled") {
            const config = configForInterface(iface);
            if (!element.checked) {
                config.domain_upstreams = [];
            }
            interfaceConfigs = interfaceConfigs.filter((item) => item.iface !== iface).concat(config);
            setDirty(true);
            renderScopeCards();
            return true;
        }
        updateInterfaceConfig(iface, field, scopeFieldValue(element, field));
        setDirty(true);
        if (field === "pihole_upstream_enabled") {
            renderScopeCards();
        }
        return true;
    }

    async function loadDnsmasq() {
        if (loading) {
            return;
        }
        loading = true;
        try {
            setState("Polling");
            const data = await HF.fetchJson("/api/services/dnsmasq");
            if (!dirty) {
                renderConfig(data);
            } else {
                const summary = data.summary || {};
                const service = data.service || {};
                currentServiceState = String(service.state || "").toUpperCase();
                setText("#dnsmasq-summary-service", service.state || "-");
                setText("#dnsmasq-summary-version", service.version || "-");
                setText("#dnsmasq-summary-pid", service.pid || "-");
                setText("#dnsmasq-summary-uptime", service.uptime || "-");
                setState("Editing", summary.updated_at || "-");
            }
        } catch (error) {
            setState("Offline");
            if (statusLabel) {
                statusLabel.textContent = error.message;
            }
        } finally {
            loading = false;
        }
    }

    async function applyDnsmasq() {
        if (statusLabel) {
            statusLabel.textContent = "applying";
        }
        const result = await HF.fetchJson("/api/services/dnsmasq", {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(formPayload()),
        });
        setDirty(false);
        if (statusLabel) {
            statusLabel.textContent = result.message || "applied";
        }
        await loadDnsmasq();
    }

    async function runServiceAction(action) {
        const resolvedAction = action === "start-restart" && currentServiceState === "RUNNING" ? "restart" : action === "start-restart" ? "start" : action;
        if (statusLabel) {
            statusLabel.textContent = resolvedAction;
        }
        await HF.fetchJson("/api/services/status/armfirewall-dnsmasq/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({action: resolvedAction}),
        });
        await loadDnsmasq();
    }

    function openActionModal(action, label, run) {
        pendingAction = {action, run};
        if (actionTitle) {
            actionTitle.textContent = label;
        }
        if (actionMessage) {
            actionMessage.textContent = `${label}?`;
        }
        if (actionConfirm) {
            actionConfirm.textContent = action === "stop" ? "Stop" : "Confirm";
            actionConfirm.classList.toggle("danger", action === "stop");
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

    async function runPendingAction() {
        if (!pendingAction || !actionConfirm) {
            return;
        }
        actionConfirm.disabled = true;
        try {
            await pendingAction.run();
            closeActionModal();
        } catch (error) {
            if (actionMessage) {
                actionMessage.textContent = error.message;
            }
        } finally {
            actionConfirm.disabled = false;
        }
    }

    if (form) {
        form.addEventListener("input", (event) => {
            if (event.target.closest("[data-scope-field]")) {
                handleScopeFieldChange(event.target);
                return;
            }
            if (event.target.closest("[data-dnsmasq-scope-domain], [data-dnsmasq-scope-servers]")) {
                return;
            }
            if (event.target.closest("#dnsmasq-domain-upstream-domain, #dnsmasq-domain-upstream-servers")) {
                return;
            }
            setDirty(true);
            syncPiholeUpstreamState();
            syncCurrentConfigFromForm();
            renderScopeCards();
        });

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!dirty) {
                return;
            }
            openActionModal("apply", "Apply Dnsmasq configuration", applyDnsmasq);
        });
    }

    document.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-dnsmasq-action]");
        if (actionButton) {
            const action = actionButton.dataset.dnsmasqAction;
            const label = action === "start-restart" ? "START / RESTART Dnsmasq service" : `${HF.text(action).toUpperCase()} Dnsmasq service`;
            openActionModal(action, label, () => runServiceAction(action));
            return;
        }

        const tabButton = event.target.closest("[data-dnsmasq-tab]");
        if (tabButton) {
            showTab(tabButton.dataset.dnsmasqTab);
            return;
        }

        const addInterfaceButton = event.target.closest("#dnsmasq-interface-add");
        if (addInterfaceButton) {
            addSelectedInterface();
            return;
        }

        const removeInterfaceButton = event.target.closest("[data-dnsmasq-interface-remove]");
        if (removeInterfaceButton) {
            removeInterface(removeInterfaceButton.dataset.dnsmasqInterfaceRemove);
            return;
        }

        const addScopeDomainButton = event.target.closest("[data-dnsmasq-scope-domain-add]");
        if (addScopeDomainButton) {
            addScopeDomainUpstream(addScopeDomainButton);
            return;
        }

        const removeScopeDomainButton = event.target.closest("[data-dnsmasq-scope-domain-remove]");
        if (removeScopeDomainButton) {
            removeScopeDomainUpstream(removeScopeDomainButton);
            return;
        }

        const addDomainUpstreamButton = event.target.closest("#dnsmasq-domain-upstream-add");
        if (addDomainUpstreamButton) {
            addDomainUpstream();
            return;
        }

        const removeDomainUpstreamButton = event.target.closest("[data-dnsmasq-domain-upstream-remove]");
        if (removeDomainUpstreamButton) {
            removeDomainUpstream(Number(removeDomainUpstreamButton.dataset.dnsmasqDomainUpstreamRemove));
            return;
        }

        if (event.target.closest("[data-dnsmasq-modal-cancel]") || event.target === actionModal) {
            closeActionModal();
        }
    });

    window.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeActionModal();
        }
    });

    if (actionConfirm) {
        actionConfirm.addEventListener("click", runPendingAction);
    }

    showTab("dns");
    setDirty(false);
    loadDnsmasq();
    setInterval(loadDnsmasq, POLL_MS);
}());
