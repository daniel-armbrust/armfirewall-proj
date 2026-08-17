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
    const ipv6RaScopeList = document.querySelector("#dnsmasq-ipv6-ra-scope-list");
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
    const viewButtons = Array.from(document.querySelectorAll("[data-dnsmasq-view]"));
    const workRequestsPanel = document.querySelector("#dnsmasq-work-requests-panel");
    const workRequestsBody = document.querySelector("#dnsmasq-work-requests-body");
    const workRequestsCount = document.querySelector("#dnsmasq-work-requests-count");
    const dhcpLeasesPanel = document.querySelector("#dnsmasq-dhcp-leases-panel");
    const dhcpLeasesBody = document.querySelector("#dnsmasq-dhcp-leases-body");
    const dhcpLeasesSummary = document.querySelector("#dnsmasq-dhcp-leases-summary");
    const dhcpLeasesSearch = document.querySelector("#dnsmasq-dhcp-leases-search");
    const addStaticAddressButton = document.querySelector("#dnsmasq-add-static-address");
    const staticLeaseModal = document.querySelector("#dnsmasq-static-lease-modal");
    const staticLeaseMac = document.querySelector("#dnsmasq-static-lease-mac");
    const staticLeaseIp = document.querySelector("#dnsmasq-static-lease-ip");
    const staticLeaseStatus = document.querySelector("#dnsmasq-static-lease-status");
    const staticLeaseApply = document.querySelector("#dnsmasq-static-lease-apply");
    const WORK_REQUESTS_POLL_MS = 5000;
    const DHCP_LEASES_POLL_MS = 5000;
    const DHCP_LEASE_SEARCH_INVALID_CHARS_RE = /[^a-zA-Z0-9.:-]/g;
    const ALL_INTERFACES = "__all__";
    const ALL_INTERFACES_LABEL = "Global configuration applied to all interfaces";
    const DNS_DOMAIN_LABEL_RE = /^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$/;
    let loading = false;
    let workRequestsLoading = false;
    let workRequestsPollTimer = null;
    let dhcpLeasesLoading = false;
    let dhcpLeasesPollTimer = null;
    let dhcpLeases = [];
    let dirty = false;
    let pendingAction = null;
    let availableInterfaces = [];
    let activeInterfaces = [];
    let domainUpstreams = [];
    let interfaceConfigs = [];
    let currentConfig = {};

    function setDhcpLeaseControlsEnabled(enabled) {
        const controlsEnabled = Boolean(enabled);
        if (dhcpLeasesSearch) {
            dhcpLeasesSearch.disabled = !controlsEnabled;
        }
        if (addStaticAddressButton) {
            addStaticAddressButton.disabled = !controlsEnabled;
        }
    }

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

    function clearFormStatus() {
        if (!statusLabel) {
            return;
        }
        statusLabel.textContent = "";
        statusLabel.classList.remove("error");
        statusLabel.hidden = true;
    }

    function showFormError(message) {
        if (!statusLabel) {
            return;
        }
        statusLabel.textContent = message;
        statusLabel.classList.add("error");
        statusLabel.hidden = false;
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
            element.value = value === null || value === undefined ? "" : String(value);
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

    function syncAdGuardHomeUpstreamState() {
        const upstream = document.querySelector("#dnsmasq-upstream-dns");
        const enabled = checkedValue("#dnsmasq-adguardhome-upstream");
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

    function isValidDnsDomain(value) {
        const domain = HF.text(value).trim().replace(/\.$/, "");
        if (!domain || domain.length > 253 || domain.includes("..") || isValidIpAddress(domain)) {
            return false;
        }
        const labels = domain.split(".");
        if (labels.length < 2) {
            return false;
        }
        return labels.every((label) => DNS_DOMAIN_LABEL_RE.test(label));
    }

    function isValidIpv4Address(value) {
        const parts = HF.text(value).trim().split(".");
        return parts.length === 4 && parts.every((part) => {
            if (!/^\d+$/.test(part)) {
                return false;
            }
            const number = Number(part);
            return number >= 0 && number <= 255 && String(number) === String(Number(part));
        });
    }

    function isValidIpv6Address(value) {
        const text = HF.text(value).trim();
        return text.includes(":") && /^[0-9A-Fa-f:.]+$/.test(text) && text.split(":").length <= 8;
    }

    function isValidIpAddress(value) {
        return isValidIpv4Address(value) || isValidIpv6Address(value);
    }

    function invalidUpstream(upstreams) {
        return upstreams.find((server) => !isValidIpAddress(server));
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
        return name;
    }

    function activeInterfaceNames() {
        if (activeInterfaces.includes(ALL_INTERFACES)) {
            return [ALL_INTERFACES];
        }
        return uniqueInterfaceNames(activeInterfaces);
    }

    function uniqueInterfaceNames(values) {
        const seen = new Set();
        const names = [];
        (values || []).forEach((value) => {
            const name = HF.text(value).trim();
            if (name && !seen.has(name)) {
                seen.add(name);
                names.push(name);
            }
        });
        return names;
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
            dns_enabled: false,
            local_domain: "armfirewall.local",
            upstream_dns_servers: [],
            domain_upstreams: [],
            forwarded_domains_enabled: false,
            adguardhome_upstream_enabled: false,
            cache_size: 1000,
            expand_hosts: true,
            domain_needed: true,
            bogus_priv: true,
            dhcp_enabled: Boolean(currentConfig.dhcp_enabled),
            dhcp_range_start: currentConfig.dhcp_range_start || "",
            dhcp_range_end: currentConfig.dhcp_range_end || "",
            lease_time: currentConfig.lease_time || "12h",
            dhcp_authoritative: currentConfig.dhcp_authoritative !== false,
            ipv6_ra_enabled: false,
            ipv6_ra_names: true,
            ipv6_ra_lifetime: "4h",
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
        domainUpstreams = currentConfig.domain_upstreams || [];
    }

    function globalDnsConfig() {
        return {
            dns_enabled: Boolean(currentConfig.dns_enabled),
            local_domain: currentConfig.local_domain || "armfirewall.local",
            upstream_dns_servers: [...(currentConfig.upstream_dns_servers || ["1.1.1.1", "8.8.8.8"])],
            domain_upstreams: (currentConfig.domain_upstreams || []).map((item) => ({domain: item.domain, upstreams: [...(item.upstreams || [])]})),
            forwarded_domains_enabled: Boolean(currentConfig.forwarded_domains_enabled || (currentConfig.domain_upstreams || []).length),
            adguardhome_upstream_enabled: Boolean(currentConfig.adguardhome_upstream_enabled),
            cache_size: currentConfig.cache_size || 1000,
            expand_hosts: currentConfig.expand_hosts !== false,
            domain_needed: currentConfig.domain_needed !== false,
            bogus_priv: currentConfig.bogus_priv !== false,
        };
    }

    function updateGlobalDnsConfig(field, value) {
        currentConfig[field] = value;
        if (field === "adguardhome_upstream_enabled" && value) {
            currentConfig.domain_upstreams = [];
            currentConfig.forwarded_domains_enabled = false;
        }
        domainUpstreams = currentConfig.domain_upstreams || [];
    }

    function updateInterfaceConfig(name, field, value) {
        const config = configForInterface(name);
        config[field] = value;
        if (field === "adguardhome_upstream_enabled" && value) {
            config.domain_upstreams = [];
        }
        interfaceConfigs = interfaceConfigs.filter((item) => item.iface !== name).concat(config);
        domainUpstreams = config.domain_upstreams || [];
    }

    function suggestedDhcpRange(ifaceName) {
        const iface = interfaceMeta(ifaceName);
        const address = (iface.addresses || []).find((item) => item.addr_family === "ipv4" && item.addr);
        if (!address) {
            return null;
        }
        const octets = HF.text(address.addr).split(".").map(Number);
        const prefixLength = Number(address.prefixlen);
        if (octets.length !== 4 || octets.some((item) => !Number.isInteger(item) || item < 0 || item > 255)
            || !Number.isInteger(prefixLength) || prefixLength < 1 || prefixLength > 30) {
            return null;
        }
        const addressNumber = octets.reduce((value, octet) => value * 256 + octet, 0);
        const subnetSize = 2 ** (32 - prefixLength);
        const networkAddress = Math.floor(addressNumber / subnetSize) * subnetSize;
        const firstUsableAddress = networkAddress + 1;
        const lastUsableAddress = networkAddress + subnetSize - 2;
        const preferredStartAddress = networkAddress + 10;
        const startAddress = Math.max(firstUsableAddress, Math.min(preferredStartAddress, lastUsableAddress));

        return {
            start: ipv4AddressFromNumber(startAddress),
            end: ipv4AddressFromNumber(lastUsableAddress),
        };
    }

    function ipv4AddressFromNumber(value) {
        return [24, 16, 8, 0].map((shift) => Math.floor(value / (2 ** shift)) % 256).join(".");
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
        const config = globalDnsConfig();
        const forwardedEnabled = !config.adguardhome_upstream_enabled && (Boolean(config.forwarded_domains_enabled) || (config.domain_upstreams || []).length > 0);
        dnsScopeList.innerHTML = `
            <section class="dnsmasq-scope-card" data-dnsmasq-scope="dns-global">
                <div class="dnsmasq-scope-head">
                    <strong>DNS configuration</strong>
                    <span><b>Global DNS configuration</b> / applied to every listen interface</span>
                </div>
                <div class="form-grid dnsmasq-scope-form">
                    <label class="field">
                        <span>DNS enabled</span>
                        <select data-global-dns-field="dns_enabled">
                            <option value="1"${selectedAttr(config.dns_enabled ? "1" : "0", "1")}>enabled</option>
                            <option value="0"${selectedAttr(config.dns_enabled ? "1" : "0", "0")}>disabled</option>
                        </select>
                    </label>
                    <label class="field">
                        <span>LAN local domain</span>
                        <input data-global-dns-field="local_domain" type="text" autocomplete="off" value="${fieldValue(config.local_domain, "armfirewall.local")}">
                    </label>
                    <label class="field">
                        <span>Cache size</span>
                        <input data-global-dns-field="cache_size" type="number" min="0" max="1000000" value="${fieldValue(config.cache_size, 1000)}">
                    </label>
                    <label class="field">
                        <span>Expand hosts</span>
                        <select data-global-dns-field="expand_hosts">
                            <option value="1"${selectedAttr(config.expand_hosts ? "1" : "0", "1")}>enabled</option>
                            <option value="0"${selectedAttr(config.expand_hosts ? "1" : "0", "0")}>disabled</option>
                        </select>
                    </label>
                    <label class="field">
                        <span>Domain needed</span>
                        <select data-global-dns-field="domain_needed">
                            <option value="1"${selectedAttr(config.domain_needed ? "1" : "0", "1")}>enabled</option>
                            <option value="0"${selectedAttr(config.domain_needed ? "1" : "0", "0")}>disabled</option>
                        </select>
                    </label>
                    <label class="field">
                        <span>Bogus priv</span>
                        <select data-global-dns-field="bogus_priv">
                            <option value="1"${selectedAttr(config.bogus_priv ? "1" : "0", "1")}>enabled</option>
                            <option value="0"${selectedAttr(config.bogus_priv ? "1" : "0", "0")}>disabled</option>
                        </select>
                    </label>
                    <label class="field wide">
                        <span>Default upstream DNS servers</span>
                        <textarea data-global-dns-field="upstream_dns_servers" rows="3" spellcheck="false"${config.adguardhome_upstream_enabled ? " disabled" : ""}>${fieldValue((config.upstream_dns_servers || []).join("\n"))}</textarea>
                    </label>
                    <label class="check-line wide">
                        <input data-global-dns-field="adguardhome_upstream_enabled" type="checkbox"${checkedAttr(config.adguardhome_upstream_enabled)}>
                        <span>Enable DNS Filtering Upstream?</span>
                    </label>
                    <label class="check-line wide">
                        <input data-global-dns-field="forwarded_domains_enabled" type="checkbox"${checkedAttr(forwardedEnabled)}${config.adguardhome_upstream_enabled ? " disabled" : ""}>
                        <span>Enable forwarded domains?</span>
                    </label>
                    <label class="field dnsmasq-forwarded-domain-row"${forwardedEnabled ? "" : " hidden"}>
                        <span>Forwarded domain</span>
                        <input data-dnsmasq-scope-domain type="text" autocomplete="off" placeholder="empresa.local" pattern="(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\\.)+[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?" title="Use a valid DNS domain such as empresa.local.">
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
    }

    function renderDhcpScopeCards() {
        if (!dhcpScopeList) {
            return;
        }
        const names = uniqueInterfaceNames(activeInterfaceNames());
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
                            <input data-scope-field="dhcp_range_start" type="text" inputmode="decimal" pattern="[0-9.]+" maxlength="15" autocomplete="off" value="${fieldValue(config.dhcp_range_start)}"${config.dhcp_enabled ? "" : " disabled"}>
                        </label>
                        <label class="field">
                            <span>DHCP range end</span>
                            <input data-scope-field="dhcp_range_end" type="text" inputmode="decimal" pattern="[0-9.]+" maxlength="15" autocomplete="off" value="${fieldValue(config.dhcp_range_end)}"${config.dhcp_enabled ? "" : " disabled"}>
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

    function renderIpv6RaScopeCards() {
        if (!ipv6RaScopeList) {
            return;
        }
        const names = uniqueInterfaceNames(activeInterfaceNames()).filter((name) => {
            const iface = interfaceMeta(name);
            return name !== ALL_INTERFACES && (iface.addresses || []).some((address) => {
                const value = HF.text(address.addr).toLowerCase();
                return address.addr_family === "ipv6" && !value.startsWith("fe80:") && value !== "::1";
            });
        });
        if (!names.length) {
            ipv6RaScopeList.innerHTML = `
                <div class="terminal-empty"><span class="prompt">$</span><span>add an interface with a routable IPv6 prefix to configure Router Advertisements</span></div>
            `;
            return;
        }
        ipv6RaScopeList.innerHTML = names.map((name) => {
            const config = configForInterface(name);
            return `
                <section class="dnsmasq-scope-card" data-dnsmasq-scope="ipv6-ra" data-iface="${HF.escapeHtml(name)}">
                    <div class="dnsmasq-scope-head">
                        <strong>IPv6 Router Advertisement</strong>
                        <span><b>${HF.escapeHtml(interfaceDisplayName(name))}</b> / SLAAC stateless</span>
                    </div>
                    <div class="form-grid dnsmasq-scope-form">
                        <label class="field">
                            <span>Router Advertisements</span>
                            <select data-scope-field="ipv6_ra_enabled">
                                <option value="1"${selectedAttr(config.ipv6_ra_enabled ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.ipv6_ra_enabled ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>Register hostnames</span>
                            <select data-scope-field="ipv6_ra_names">
                                <option value="1"${selectedAttr(config.ipv6_ra_names ? "1" : "0", "1")}>enabled</option>
                                <option value="0"${selectedAttr(config.ipv6_ra_names ? "1" : "0", "0")}>disabled</option>
                            </select>
                        </label>
                        <label class="field">
                            <span>RA lifetime</span>
                            <input data-scope-field="ipv6_ra_lifetime" type="text" autocomplete="off" value="${fieldValue(config.ipv6_ra_lifetime, "4h")}">
                        </label>
                    </div>
                </section>
            `;
        }).join("");
    }

    function renderScopeCards() {
        renderDnsScopeCards();
        renderDhcpScopeCards();
        renderIpv6RaScopeCards();
        removeDuplicateScopeCards();
    }

    function removeDuplicateScopeCards() {
        const seen = new Set();
        document.querySelectorAll(".dnsmasq-scope-card[data-dnsmasq-scope][data-iface]").forEach((card) => {
            const key = `${card.dataset.dnsmasqScope}:${card.dataset.iface}`;
            if (seen.has(key)) {
                card.remove();
                return;
            }
            seen.add(key);
        });
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
            ? ['<option value="" selected>Select interface</option>', ...options.map((iface) => {
                if (iface.name === ALL_INTERFACES) {
                    return `<option value="${HF.escapeHtml(iface.name)}">${HF.escapeHtml(iface.description)}</option>`;
                }
                const role = HF.text(iface.role || "UNKNOWN");
                const description = HF.text(iface.description || "-");
                const label = `${HF.text(iface.name)} (${role}) - ${description}`;
                return `<option value="${HF.escapeHtml(iface.name)}">${HF.escapeHtml(label)}</option>`;
            })].join("")
            : '<option value="">no interfaces available</option>';
        if (interfaceAddButton) {
            interfaceAddButton.disabled = !options.length || !interfacePicker.value;
        }
    }

    function renderActiveInterfaces() {
        if (!activeInterfacesBody) {
            return;
        }
        activeInterfaces = uniqueInterfaceNames(activeInterfaceNames());
        if (!activeInterfaces.length) {
            activeInterfacesBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no active interfaces</span></div></td>
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
                        <td colspan="4"><strong>${HF.escapeHtml(iface.description)}</strong></td>
                        <td><button class="text-button compact danger" type="button" data-dnsmasq-interface-remove="${HF.escapeHtml(name)}">Remove</button></td>
                    </tr>
                `;
            }
            const displayName = interfaceDisplayName(name);
            const ipv4Addresses = interfaceAddressLabel(iface, "ipv4");
            const ipv6Addresses = interfaceAddressLabel(iface, "ipv6");
            return `
                <tr>
                    <td><strong>${HF.escapeHtml(displayName)}</strong></td>
                    <td>${HF.escapeHtml(iface.role || "-")}</td>
                    <td>${ipv4Addresses}</td>
                    <td>${ipv6Addresses}</td>
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

    function interfaceAddressLabel(iface, family) {
        const addresses = Array.isArray(iface.addresses) ? iface.addresses : [];
        const values = addresses
            .filter((address) => address.addr_family === family && address.addr)
            .map((address) => `${HF.text(address.addr)}/${HF.text(address.prefixlen)}`);
        if (!values.length) {
            return "-";
        }
        const fullValue = values.join(", ");
        const shortValue = fullValue.length > 24 ? `${fullValue.slice(0, 24)}...` : fullValue;
        return `<span class="dnsmasq-address" title="${HF.escapeHtml(fullValue)}">${HF.escapeHtml(shortValue)}</span>`;
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
            activeInterfaces = uniqueInterfaceNames(activeInterfaces);
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
            showFormError("domain and upstream servers are required");
            return;
        }
        if (!isValidDnsDomain(domain)) {
            showFormError("Forwarded domain must be a valid DNS domain.");
            domainUpstreamDomain?.focus();
            return;
        }
        const badUpstream = invalidUpstream(upstreams);
        if (badUpstream) {
            showFormError(`Invalid upstream DNS server: ${badUpstream}`);
            domainUpstreamServers?.focus();
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
        const card = button.closest("[data-dnsmasq-scope='dns-global']");
        if (!card) {
            return;
        }
        const domainInput = card.querySelector("[data-dnsmasq-scope-domain]");
        const serversInput = card.querySelector("[data-dnsmasq-scope-servers]");
        const domain = HF.text(domainInput?.value).trim().replace(/\.$/, "");
        const upstreams = splitServerTokens(serversInput?.value || "");
        [domainInput, serversInput].forEach((element) => {
            if (element) {
                element.setCustomValidity("");
                element.classList.remove("is-invalid");
                element.closest(".field")?.classList.remove("is-invalid");
            }
        });
        if (!domain) {
            showScopeValidationError(domainInput, "Forwarded domain is required.");
            return;
        }
        if (!isValidDnsDomain(domain)) {
            showScopeValidationError(domainInput, "Forwarded domain must be a valid DNS domain.");
            return;
        }
        if (!upstreams.length) {
            showScopeValidationError(serversInput, "Forward to DNS servers is required.");
            return;
        }
        const badUpstream = invalidUpstream(upstreams);
        if (badUpstream) {
            showScopeValidationError(serversInput, `Invalid upstream DNS server: ${badUpstream}`);
            return;
        }
        clearFormStatus();
        const config = globalDnsConfig();
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
        updateGlobalDnsConfig("domain_upstreams", config.domain_upstreams);
        setDirty(true);
        renderScopeCards();
    }

    function showScopeValidationError(element, message) {
        showFormError(message);
        if (!element) {
            return;
        }
        element.setCustomValidity(message);
        element.classList.add("is-invalid");
        element.closest(".field")?.classList.add("is-invalid");
        element.reportValidity();
        element.focus();
    }

    function removeScopeDomainUpstream(button) {
        const card = button.closest("[data-dnsmasq-scope='dns-global']");
        if (!card) {
            return;
        }
        const config = globalDnsConfig();
        config.domain_upstreams = (config.domain_upstreams || []).filter((_, index) => index !== Number(button.dataset.dnsmasqScopeDomainRemove));
        updateGlobalDnsConfig("domain_upstreams", config.domain_upstreams);
        setDirty(true);
        renderScopeCards();
    }

    function renderConfig(data) {
        const config = data.config || {};
        currentConfig = config;
        const summary = data.summary || {};
        const service = data.service || {};
        const dhcpConfigured = Boolean(config.dhcp_enabled) || (config.interface_configs || []).some((item) => item.dhcp_enabled);
        const dhcpActive = dhcpConfigured && String(service.state || "").toUpperCase() === "RUNNING";
        renderInterfaces(data.interfaces || [], config.listen_interfaces || []);
        setDhcpLeaseControlsEnabled(dhcpActive);

        setBoolean("#dnsmasq-dns-enabled", config.dns_enabled);
        setBoolean("#dnsmasq-dhcp-enabled", config.dhcp_enabled);
        setValue("#dnsmasq-local-domain", config.local_domain);
        setValue("#dnsmasq-cache-size", config.cache_size);
        setValue("#dnsmasq-upstream-dns", (config.upstream_dns_servers || []).join("\n"));
        renderDomainUpstreams(config.domain_upstreams || []);
        setChecked("#dnsmasq-adguardhome-upstream", config.adguardhome_upstream_enabled);
        syncAdGuardHomeUpstreamState();
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
                    <td colspan="6">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no dnsmasq work requests</span></div>
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
                    <td>${HF.escapeHtml(request.updated_at)}</td>
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
            const data = await HF.fetchJson("/api/services/dnsmasq/work-requests");
            renderWorkRequests(data);
            if (!workRequestsPanel.hidden) {
                scheduleWorkRequestsPolling();
            }
        } catch (error) {
            if (workRequestsBody) {
                workRequestsBody.innerHTML = `
                    <tr>
                        <td colspan="6">
                            <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
                        </td>
                    </tr>
                `;
            }
        } finally {
            workRequestsLoading = false;
        }
    }

    function scheduleWorkRequestsPolling() {
        clearTimeout(workRequestsPollTimer);
        workRequestsPollTimer = window.setTimeout(loadWorkRequests, WORK_REQUESTS_POLL_MS);
    }

    function stopWorkRequestsPolling() {
        clearTimeout(workRequestsPollTimer);
        workRequestsPollTimer = null;
    }

    function renderDhcpLeases(data) {
        setDhcpLeaseControlsEnabled(data.dhcp_active);
        dhcpLeases = data.leases || [];
        const search = String(dhcpLeasesSearch?.value || "").trim().toLowerCase();
        const leases = dhcpLeases.filter((lease) => !search || [
            lease.ip_address,
            lease.mac_address,
            lease.hostname,
            lease.client_id,
        ].some((value) => String(value || "").toLowerCase().includes(search)));
        if (dhcpLeasesSummary) {
            dhcpLeasesSummary.textContent = `leases=${leases.length}`;
        }
        if (!dhcpLeasesBody) {
            return;
        }
        if (!data.dhcp_active) {
            dhcpLeasesBody.innerHTML = `<tr><td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(data.message || "DHCP service is not active or configured.")}</span></div></td></tr>`;
            return;
        }
        if (!leases.length) {
            const message = search ? "No DHCP lease matches the search." : data.message || "No DHCP leases found.";
            dhcpLeasesBody.innerHTML = `<tr><td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(message)}</span></div></td></tr>`;
            return;
        }
        dhcpLeasesBody.innerHTML = leases.map((lease) => `
            <tr>
                <td>${HF.escapeHtml(lease.ip_address)}</td>
                <td>${HF.escapeHtml(lease.mac_address)}</td>
                <td>${HF.escapeHtml(lease.hostname)}</td>
                <td>${HF.escapeHtml(lease.client_id)}</td>
                <td>${HF.escapeHtml(lease.expires_at)}</td>
                <td>${lease.is_static
                    ? `<button class="text-button compact danger" type="button" data-dnsmasq-remove-static-mac="${HF.escapeHtml(lease.mac_address)}" data-dnsmasq-remove-static-ip="${HF.escapeHtml(lease.ip_address)}">Remove Static</button>`
                    : `<button class="text-button compact" type="button" data-dnsmasq-make-static-mac="${HF.escapeHtml(lease.mac_address)}" data-dnsmasq-make-static-ip="${HF.escapeHtml(lease.ip_address)}">Make Static</button>`}</td>
            </tr>
        `).join("");
    }

    async function loadDhcpLeases() {
        if (dhcpLeasesLoading || !dhcpLeasesPanel || dhcpLeasesPanel.hidden) {
            return;
        }
        dhcpLeasesLoading = true;
        try {
            const data = await HF.fetchJson("/api/services/dnsmasq/leases");
            renderDhcpLeases(data);
            if (data.dhcp_active && !dhcpLeasesPanel.hidden) {
                scheduleDhcpLeasesPolling();
            }
        } catch (error) {
            setDhcpLeaseControlsEnabled(false);
            if (dhcpLeasesSummary) {
                dhcpLeasesSummary.textContent = "Offline";
            }
            if (dhcpLeasesBody) {
                dhcpLeasesBody.innerHTML = `<tr><td colspan="6"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td></tr>`;
            }
        } finally {
            dhcpLeasesLoading = false;
        }
    }

    function scheduleDhcpLeasesPolling() {
        clearTimeout(dhcpLeasesPollTimer);
        dhcpLeasesPollTimer = window.setTimeout(loadDhcpLeases, DHCP_LEASES_POLL_MS);
    }

    function stopDhcpLeasesPolling() {
        clearTimeout(dhcpLeasesPollTimer);
        dhcpLeasesPollTimer = null;
    }

    function openStaticLeaseModal(macAddress = "", ipAddress = "") {
        if (staticLeaseMac) staticLeaseMac.value = macAddress;
        if (staticLeaseIp) staticLeaseIp.value = ipAddress;
        if (staticLeaseStatus) {
            staticLeaseStatus.hidden = true;
            staticLeaseStatus.textContent = "";
            staticLeaseStatus.classList.remove("error");
        }
        if (staticLeaseModal) staticLeaseModal.hidden = false;
    }

    function closeStaticLeaseModal() {
        if (staticLeaseModal) staticLeaseModal.hidden = true;
    }

    async function queueStaticLease(macAddress, ipAddress) {
        await HF.fetchJson("/api/services/dnsmasq/static-leases", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({mac_address: macAddress, ip_address: ipAddress}),
        });
        showWorkRequests();
        await loadWorkRequests();
        await loadDnsmasq();
    }

    async function removeStaticLease(macAddress, ipAddress) {
        await HF.fetchJson("/api/services/dnsmasq/static-leases", {
            method: "DELETE",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({mac_address: macAddress, ip_address: ipAddress}),
        });
        showWorkRequests();
        await loadWorkRequests();
        await loadDnsmasq();
    }

    async function applyStaticLease() {
        if (!staticLeaseApply) return;
        staticLeaseApply.disabled = true;
        try {
            await queueStaticLease(staticLeaseMac?.value || "", staticLeaseIp?.value || "");
            closeStaticLeaseModal();
        } catch (error) {
            if (staticLeaseStatus) {
                staticLeaseStatus.textContent = error.message;
                staticLeaseStatus.classList.add("error");
                staticLeaseStatus.hidden = false;
            }
        } finally {
            staticLeaseApply.disabled = false;
        }
    }

    function setActiveView(viewName) {
        const isWorkRequests = viewName === "work-requests";
        const isDhcpLeases = viewName === "dhcp-leases";
        if (workRequestsPanel) {
            workRequestsPanel.hidden = !isWorkRequests;
        }
        if (dhcpLeasesPanel) {
            dhcpLeasesPanel.hidden = !isDhcpLeases;
        }
        if (form) {
            form.hidden = isWorkRequests || isDhcpLeases;
        }
        viewButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.dnsmasqView === viewName);
        });
        if (isWorkRequests) {
            loadWorkRequests();
        } else {
            stopWorkRequestsPolling();
        }
        if (isDhcpLeases) {
            loadDhcpLeases();
        } else {
            stopDhcpLeasesPolling();
        }
    }

    function showWorkRequests() {
        if (!workRequestsPanel) {
            return;
        }
        setActiveView("work-requests");
        requestAnimationFrame(() => {
            document.querySelector("#main-content")?.scrollTo({top: 0, behavior: "smooth"});
            document.documentElement.scrollTo({top: 0, behavior: "smooth"});
            document.body.scrollTo({top: 0, behavior: "smooth"});
            window.scrollTo({top: 0, behavior: "smooth"});
        });
    }

    function formPayload() {
        syncInterfaceConfigs();
        const dnsConfig = globalDnsConfig();
        return {
            dns_enabled: Boolean(dnsConfig.dns_enabled),
            dhcp_enabled: interfaceConfigs.some((item) => item.dhcp_enabled),
            listen_interfaces: selectedInterfaces(),
            interface_configs: interfaceConfigs,
            local_domain: dnsConfig.local_domain || "",
            upstream_dns_servers: dnsConfig.upstream_dns_servers || [],
            domain_upstreams: dnsConfig.domain_upstreams || [],
            adguardhome_upstream_enabled: Boolean(dnsConfig.adguardhome_upstream_enabled),
            dhcp_range_start: "",
            dhcp_range_end: "",
            lease_time: "",
            cache_size: dnsConfig.cache_size || 0,
            expand_hosts: Boolean(dnsConfig.expand_hosts),
            domain_needed: Boolean(dnsConfig.domain_needed),
            bogus_priv: Boolean(dnsConfig.bogus_priv),
            dhcp_authoritative: interfaceConfigs.some((item) => item.dhcp_authoritative),
            ipv6_ra_enabled: interfaceConfigs.some((item) => item.ipv6_ra_enabled),
            ipv6_ra_names: interfaceConfigs.some((item) => item.ipv6_ra_names),
            ipv6_ra_lifetime: "4h",
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
        if (field === "dhcp_range_start" || field === "dhcp_range_end") {
            element.value = element.value.replace(/[^0-9.]/g, "");
        }
        if (field === "forwarded_domains_enabled") {
            const config = configForInterface(iface);
            if (!element.checked) {
                config.domain_upstreams = [];
            }
            config.forwarded_domains_enabled = element.checked;
            interfaceConfigs = interfaceConfigs.filter((item) => item.iface !== iface).concat(config);
            setDirty(true);
            renderScopeCards();
            return true;
        }
        const value = scopeFieldValue(element, field);
        updateInterfaceConfig(iface, field, value);
        setDirty(true);
        if (field === "dhcp_enabled") {
            const config = configForInterface(iface);
            if (value && !config.dhcp_range_start && !config.dhcp_range_end) {
                const range = suggestedDhcpRange(iface);
                if (range) {
                    updateInterfaceConfig(iface, "dhcp_range_start", range.start);
                    updateInterfaceConfig(iface, "dhcp_range_end", range.end);
                }
            }
            renderScopeCards();
            return true;
        }
        if (field === "adguardhome_upstream_enabled") {
            if (scopeFieldValue(element, field)) {
                updateInterfaceConfig(iface, "forwarded_domains_enabled", false);
            }
            renderScopeCards();
        }
        return true;
    }

    function handleGlobalDnsFieldChange(element) {
        const field = element.dataset.globalDnsField;
        if (!field) {
            return false;
        }
        if (field === "forwarded_domains_enabled") {
            if (!element.checked) {
                updateGlobalDnsConfig("domain_upstreams", []);
            }
            updateGlobalDnsConfig(field, element.checked);
            setDirty(true);
            renderScopeCards();
            return true;
        }
        updateGlobalDnsConfig(field, scopeFieldValue(element, field));
        setDirty(true);
        if (field === "adguardhome_upstream_enabled") {
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
            setState("Loading");
            const data = await HF.fetchJson("/api/services/dnsmasq");
            if (!dirty) {
                renderConfig(data);
            } else {
                const summary = data.summary || {};
                const service = data.service || {};
                setText("#dnsmasq-summary-service", service.state || "-");
                setText("#dnsmasq-summary-version", service.version || "-");
                setText("#dnsmasq-summary-pid", service.pid || "-");
                setText("#dnsmasq-summary-uptime", service.uptime || "-");
                setState("Editing", summary.updated_at || "-");
            }
        } catch (error) {
            setState("Offline");
            showFormError(error.message);
        } finally {
            loading = false;
        }
    }

    async function applyDnsmasq() {
        syncInterfaceConfigs();
        clearFormStatus();
        const result = await HF.fetchJson("/api/services/dnsmasq", {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(formPayload()),
        });
        setDirty(false);
        clearFormStatus();
        showWorkRequests();
        await loadDnsmasq();
    }

    async function runServiceAction(action) {
        clearFormStatus();
        await HF.fetchJson("/api/services/status/dnsmasq/action", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({action}),
        });
        clearFormStatus();
        showWorkRequests();
        await loadWorkRequests();
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
            actionConfirm.textContent = action === "stop" ? "Stop" : action === "make-static" ? "Yes" : "Confirm";
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
            if (event.target.closest("[data-global-dns-field]")) {
                handleGlobalDnsFieldChange(event.target);
                return;
            }
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
            syncAdGuardHomeUpstreamState();
            syncCurrentConfigFromForm();
            renderScopeCards();
        });

        form.addEventListener("submit", (event) => {
            event.preventDefault();
            if (!dirty) {
                return;
            }
            openActionModal("apply", "Apply DNSMasq configuration", applyDnsmasq);
        });
    }

    document.addEventListener("click", (event) => {
        const actionButton = event.target.closest("[data-dnsmasq-action]");
        if (actionButton) {
            const action = actionButton.dataset.dnsmasqAction;
            const label = action === "start-restart" ? "START / RESTART DNSMasq service" : `${HF.text(action).toUpperCase()} DNSMasq service`;
            openActionModal(action, label, () => runServiceAction(action));
            return;
        }

        const makeStaticButton = event.target.closest("[data-dnsmasq-make-static-mac]");
        if (makeStaticButton) {
            const macAddress = makeStaticButton.dataset.dnsmasqMakeStaticMac;
            const ipAddress = makeStaticButton.dataset.dnsmasqMakeStaticIp;
            openActionModal("make-static", "Make this DHCP lease static", () => queueStaticLease(macAddress, ipAddress));
            return;
        }

        const removeStaticButton = event.target.closest("[data-dnsmasq-remove-static-mac]");
        if (removeStaticButton) {
            const macAddress = removeStaticButton.dataset.dnsmasqRemoveStaticMac;
            const ipAddress = removeStaticButton.dataset.dnsmasqRemoveStaticIp;
            openActionModal("remove-static", "Remove this static DHCP address", () => removeStaticLease(macAddress, ipAddress));
            return;
        }

        if (event.target.closest("#dnsmasq-add-static-address") && !addStaticAddressButton?.disabled) {
            openStaticLeaseModal();
            return;
        }

        const viewButton = event.target.closest("[data-dnsmasq-view]");
        if (viewButton) {
            setActiveView(viewButton.dataset.dnsmasqView || "config");
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

        if (event.target.closest("[data-dnsmasq-static-lease-cancel]") || event.target === staticLeaseModal) {
            closeStaticLeaseModal();
        }
    });

    window.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeActionModal();
            closeStaticLeaseModal();
        }
    });

    if (actionConfirm) {
        actionConfirm.addEventListener("click", runPendingAction);
    }

    if (staticLeaseApply) {
        staticLeaseApply.addEventListener("click", applyStaticLease);
    }

    if (dhcpLeasesSearch) {
        dhcpLeasesSearch.addEventListener("input", () => {
            dhcpLeasesSearch.value = dhcpLeasesSearch.value
                .replace(DHCP_LEASE_SEARCH_INVALID_CHARS_RE, "")
                .slice(0, 255);
            renderDhcpLeases({leases: dhcpLeases, dhcp_active: true});
        });
    }

    if (interfacePicker && interfaceAddButton) {
        interfacePicker.addEventListener("change", () => {
            interfaceAddButton.disabled = !interfacePicker.value;
        });
    }

    showTab("dns");
    setActiveView("config");
    setDirty(false);
    loadDnsmasq();
}());
