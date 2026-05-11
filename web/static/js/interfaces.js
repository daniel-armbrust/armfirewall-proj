(function () {
    const stateLabel = document.querySelector("#refresh-state");
    const counterList = document.querySelector("#counter-list");
    const interfaceInventoryBody = document.querySelector("#interface-inventory-body");

    function setRefreshState(state, updated = "") {
        if (!stateLabel) {
            return;
        }

        if (updated) {
            stateLabel.innerHTML = `${HF.escapeHtml(state)} / <span class="refresh-state-label">updated=</span>${HF.escapeHtml(updated)}`;
            return;
        }

        stateLabel.textContent = state;
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

    function renderInterfaceInventory(interfaces) {
        if (!interfaceInventoryBody) {
            return;
        }

        if (!interfaces.length) {
            interfaceInventoryBody.innerHTML = `
                <tr>
                    <td colspan="8">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no interfaces</span></div>
                    </td>
                </tr>
            `;
            return;
        }

        interfaceInventoryBody.innerHTML = interfaces.map((iface) => {
            const addresses = (iface.addresses || []).length
                ? iface.addresses.map((address) => `
                    <span class="address">${HF.escapeHtml(address.addr_family)} ${HF.escapeHtml(address.addr)}/${HF.escapeHtml(address.prefixlen)}</span>
                `).join("")
                : '<span class="muted">-</span>';
            const status = HF.number(iface.is_actived) === 1
                ? '<span class="status up">UP</span>'
                : '<span class="status down">DOWN</span>';
            const tooltip = interfaceTooltip(iface);

            return `
                <tr>
                    <td>
                        <div class="iface-name-cell">
                            <a class="icon-button iface-edit" href="/network/interfaces/${encodeURIComponent(iface.name)}/edit" title="Edit properties" aria-label="Edit ${HF.escapeHtml(iface.name)} properties">&#9881;</a>
                            <strong class="iface-tooltip" tabindex="0" title="${HF.escapeHtml(tooltip)}" data-tooltip="${HF.escapeHtml(tooltip)}">${HF.escapeHtml(iface.name)}</strong>
                        </div>
                    </td>
                    <td><span class="role">${HF.escapeHtml(iface.role)}</span></td>
                    <td>${status}</td>
                    <td><div class="addresses">${addresses}</div></td>
                    <td>${HF.escapeHtml(iface.mac_address)}</td>
                    <td>${HF.escapeHtml(iface.mtu)}</td>
                    <td>${HF.number(iface.speed_mbps).toLocaleString()} Mb/s ${HF.escapeHtml(iface.duplex)}</td>
                    <td>${HF.escapeHtml(iface.rx_label)} / ${HF.escapeHtml(iface.tx_label)}</td>
                </tr>
            `;
        }).join("");
    }

    async function pollTrafficCounters() {
        try {
            setRefreshState("Polling");

            const data = await HF.fetchJson("/api/traffic-counters");
            HF.renderSummary(data.summary);
            renderInterfaceInventory(data.interfaces);
            HF.renderCounterList(counterList, data.interfaces);

            setRefreshState("Live", data.summary.updated_at || "-");
        } catch (error) {
            setRefreshState("Offline");
            if (counterList) {
                counterList.innerHTML = `<div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>`;
            }
            if (interfaceInventoryBody) {
                interfaceInventoryBody.innerHTML = `
                    <tr>
                        <td colspan="8">
                            <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
                        </td>
                    </tr>
                `;
            }
        }
    }

    pollTrafficCounters();
    setInterval(pollTrafficCounters, 5000);
}());
