(function () {
    const stateLabel = document.querySelector("#neighbor-table-state");
    const tableBody = document.querySelector("#neighbor-table-body");
    const tableCount = document.querySelector("#neighbor-table-count");
    const ipSortButton = document.querySelector("#neighbor-ip-sort");
    const POLL_MS = 3000;
    let interfaceDetails = new Map();
    let lastEntries = [];
    let ipSortDirection = "asc";

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

    function stateClass(state) {
        const value = String(state || "").toUpperCase();
        if (["REACHABLE", "STALE", "DELAY", "PROBE", "PERMANENT", "NOARP"].includes(value)) {
            return "up";
        }
        if (["FAILED", "INCOMPLETE"].includes(value)) {
            return "down";
        }
        return "disabled";
    }

    function ipv4SortValue(address) {
        const parts = String(address || "").split(".");
        if (parts.length !== 4) {
            return null;
        }
        const octets = parts.map((part) => Number(part));
        if (octets.some((part) => !Number.isInteger(part) || part < 0 || part > 255)) {
            return null;
        }
        return octets.reduce((value, octet) => (value * 256) + octet, 0);
    }

    function compareIpEntries(left, right) {
        const leftFamily = String(left.addr_family || "");
        const rightFamily = String(right.addr_family || "");
        if (leftFamily !== rightFamily) {
            return leftFamily.localeCompare(rightFamily);
        }

        const leftIpv4 = ipv4SortValue(left.ip_address);
        const rightIpv4 = ipv4SortValue(right.ip_address);
        if (leftIpv4 !== null && rightIpv4 !== null && leftIpv4 !== rightIpv4) {
            return leftIpv4 - rightIpv4;
        }

        const ipCompare = String(left.ip_address || "").localeCompare(String(right.ip_address || ""), undefined, { numeric: true });
        if (ipCompare !== 0) {
            return ipCompare;
        }

        return String(left.iface || "").localeCompare(String(right.iface || ""));
    }

    function sortedEntries(entries) {
        const direction = ipSortDirection === "desc" ? -1 : 1;
        return entries.slice().sort((left, right) => compareIpEntries(left, right) * direction);
    }

    function updateSortButton() {
        if (!ipSortButton) {
            return;
        }
        const label = ipSortDirection === "asc" ? "Sort by IP address: ascending" : "Sort by IP address: descending";
        ipSortButton.textContent = ipSortDirection === "asc" ? "↑" : "↓";
        ipSortButton.setAttribute("title", label);
        ipSortButton.setAttribute("aria-label", label);
    }

    function interfaceTooltip(iface) {
        const state = HF.number(iface.is_actived) === 1 ? "UP" : "DOWN";
        const addresses = (iface.addresses || [])
            .map((address) => `${HF.text(address.addr_family).toUpperCase()} ${HF.text(address.addr)}/${HF.text(address.prefixlen)}`)
            .join(", ");

        return [
            `Interface: ${HF.text(iface.name)}`,
            `Role: ${HF.text(iface.role || "UNKNOWN")}`,
            `Description: ${HF.text(iface.description)}`,
            `MAC: ${HF.text(iface.mac_address)}`,
            `MTU: ${HF.text(iface.mtu)}`,
            `State: ${state}`,
            `Speed: ${HF.number(iface.speed_mbps).toLocaleString()} Mb/s`,
            `Duplex: ${HF.text(iface.duplex || "unknown")}`,
            addresses ? `Addresses: ${addresses}` : "Addresses: -",
        ].join("\n");
    }

    function tooltipForInterface(name) {
        const iface = interfaceDetails.get(String(name || ""));
        if (iface) {
            return interfaceTooltip(iface);
        }
        return `Interface: ${HF.text(name)}`;
    }

    async function loadInterfaceDetails() {
        try {
            const data = await HF.fetchJson("/api/interfaces");
            interfaceDetails = new Map(
                (data.interfaces || []).map((iface) => [String(iface.name || ""), iface]),
            );
        } catch (error) {
            interfaceDetails = new Map();
        }
    }

    function renderRows(entries) {
        if (!tableBody) {
            return;
        }

        if (!entries.length) {
            tableBody.innerHTML = `
                <tr>
                    <td colspan="7">
                        <div class="terminal-empty"><span class="prompt">$</span><span>neighbor table is empty</span></div>
                    </td>
                </tr>
            `;
            return;
        }

        tableBody.innerHTML = entries.map((entry) => {
            const ifaceTooltip = tooltipForInterface(entry.iface);
            return `
                <tr>
                    <td>${HF.escapeHtml(String(entry.addr_family || "").toUpperCase())}</td>
                    <td>${HF.escapeHtml(entry.ip_address)}</td>
                    <td>${HF.escapeHtml(entry.mac_address)}</td>
                    <td><span class="iface-tooltip" tabindex="0" title="${HF.escapeHtml(ifaceTooltip)}" data-tooltip="${HF.escapeHtml(ifaceTooltip)}">${HF.escapeHtml(entry.iface)}</span></td>
                    <td><span class="status ${stateClass(entry.state)}">${HF.escapeHtml(entry.state)}</span></td>
                    <td>${HF.escapeHtml(entry.flags)}</td>
                    <td><span class="arm-tooltip" tabindex="0" title="${HF.escapeHtml(entry.raw)}" data-tooltip="${HF.escapeHtml(entry.raw)}">${HF.escapeHtml(entry.raw)}</span></td>
                </tr>
            `;
        }).join("");
    }

    async function pollNeighborTable() {
        try {
            setState("Polling");
            const data = await HF.fetchJson("/api/network/neighbor-table");
            const summary = data.summary || {};
            lastEntries = data.entries || [];

            setMetric("#neighbor-summary-entries", summary.entries);
            setMetric("#neighbor-summary-interfaces", summary.interfaces);
            setMetric("#neighbor-summary-reachable", summary.reachable);
            setMetric("#neighbor-summary-families", `${HF.number(summary.ipv4)} / ${HF.number(summary.ipv6)}`);
            if (tableCount) {
                tableCount.textContent = `entries=${HF.number(summary.entries).toLocaleString()}`;
            }
            renderRows(sortedEntries(lastEntries));
            setState("Live", summary.updated_at || "-");
        } catch (error) {
            setState("Offline");
            if (tableBody) {
                tableBody.innerHTML = `
                    <tr>
                        <td colspan="7">
                            <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
                        </td>
                    </tr>
                `;
            }
        }
    }

    if (ipSortButton) {
        ipSortButton.addEventListener("click", () => {
            ipSortDirection = ipSortDirection === "asc" ? "desc" : "asc";
            updateSortButton();
            renderRows(sortedEntries(lastEntries));
        });
    }

    updateSortButton();
    loadInterfaceDetails().finally(pollNeighborTable);
    setInterval(pollNeighborTable, POLL_MS);
}());
