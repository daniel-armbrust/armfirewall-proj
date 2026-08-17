(function () {
    const stateLabel = document.querySelector("#refresh-state");
    const interfaceEditPanel = document.querySelector("[data-interface-edit]");
    const interfaceEditForm = document.querySelector("#interface-edit-form");
    const interfaceEditAddresses = document.querySelector("#interface-edit-addresses");
    const interfaceEditProc = document.querySelector("#interface-edit-proc");
    const procValueModal = document.querySelector("#proc-value-modal");
    const procValueForm = document.querySelector("#proc-value-form");
    const procValuePath = document.querySelector("#proc-value-path");
    const procValueCurrent = document.querySelector("#proc-value-current");
    const procValueStatus = document.querySelector("#proc-value-status");
    const procWorkRequestModal = document.querySelector("#proc-work-request-modal");
    const procWorkRequestId = document.querySelector("#proc-work-request-id");

    function setValue(selector, value) {
        const field = document.querySelector(selector);
        if (field) {
            field.value = HF.text(value);
        }
    }

    function renderInterfaceEditForm(iface) {
        setValue("#iface-edit-name", iface.name);
        setValue("#iface-edit-role", iface.role);
        setValue("#iface-edit-status", HF.number(iface.is_actived) === 1 ? "UP" : "DOWN");
        setValue("#iface-edit-protected", HF.number(iface.protected) === 1 ? "1" : "0");
        setValue("#iface-edit-mac", iface.mac_address);
        setValue("#iface-edit-mtu", iface.mtu);
        setValue("#iface-edit-speed", `${HF.number(iface.speed_mbps).toLocaleString()} Mb/s`);
        setValue("#iface-edit-duplex", iface.duplex);
        setValue("#iface-edit-description", iface.description);
    }

    function renderInterfaceEditAddresses(iface) {
        if (!interfaceEditAddresses) {
            return;
        }

        const countLabel = document.querySelector("#interface-edit-address-count");
        const addresses = iface.addresses || [];

        if (countLabel) {
            countLabel.textContent = `items=${addresses.length}`;
        }

        if (!addresses.length) {
            interfaceEditAddresses.innerHTML = `
                <tr><td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no addresses</span></div></td></tr>
            `;
            return;
        }

        interfaceEditAddresses.innerHTML = addresses.map((address) => `
            <tr>
                <td>${HF.escapeHtml(address.addr_family)}</td>
                <td>${HF.escapeHtml(address.addr)}</td>
                <td>${HF.escapeHtml(address.prefixlen)}</td>
                <td>${HF.escapeHtml(address.broadcast)}</td>
                <td>${HF.escapeHtml(address.scopeid)}</td>
            </tr>
        `).join("");
    }

    function renderInterfaceEditProc(rows) {
        if (!interfaceEditProc) {
            return;
        }

        const countLabel = document.querySelector("#interface-edit-proc-count");

        if (countLabel) {
            countLabel.textContent = `items=${rows.length}`;
        }

        if (!rows.length) {
            interfaceEditProc.innerHTML = `
                <div class="terminal-empty"><span class="prompt">$</span><span>no proc values</span></div>
            `;
            return;
        }

        const familyOrder = ["ipv4", "ipv6"];
        const grouped = rows.reduce((accumulator, row) => {
            const family = HF.text(row.addr_family).toLowerCase();
            accumulator[family] = accumulator[family] || [];
            accumulator[family].push(row);
            return accumulator;
        }, {});

        interfaceEditProc.innerHTML = familyOrder.map((family) => {
            const familyRows = grouped[family] || [];
            const title = family === "ipv4" ? "IPv4" : "IPv6";

            return `
                <section class="proc-family">
                    <h3>${title}</h3>
                    ${familyRows.length ? `
                        <div class="table-wrap">
                            <table class="data-table proc-table">
                                <thead>
                                    <tr>
                                        <th></th>
                                        <th>PATH</th>
                                        <th>Description</th>
                                        <th>Default</th>
                                        <th>User defined</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${familyRows.map((row) => `
                                        <tr>
                                            <td>
                                                <button class="icon-button proc-edit" type="button" title="Edit user defined value" aria-label="Edit ${HF.escapeHtml(row.proc_path)}" data-proc-path="${HF.escapeHtml(row.proc_path)}" data-proc-value="${HF.escapeHtml(row.desired_value)}">&#9998;</button>
                                            </td>
                                            <td><code class="proc-path">${HF.escapeHtml(row.proc_path)}</code></td>
                                            <td>${HF.escapeHtml(row.description)}</td>
                                            <td>${HF.escapeHtml(row.default_value)}</td>
                                            <td>${HF.escapeHtml(row.desired_value)}</td>
                                        </tr>
                                    `).join("")}
                                </tbody>
                            </table>
                        </div>
                    ` : `
                        <div class="terminal-empty"><span class="prompt">$</span><span>no ${title} proc values</span></div>
                    `}
                </section>
            `;
        }).join("");
    }

    function openProcValueModal(procPath, currentValue) {
        if (!procValueModal || !procValuePath || !procValueCurrent) {
            return;
        }

        procValuePath.value = procPath;
        procValueCurrent.value = currentValue;
        if (procValueStatus) {
            procValueStatus.textContent = "";
        }
        procValueModal.hidden = false;
        procValueCurrent.focus();
    }

    function openProcWorkRequestModal(workRequestId) {
        if (!procWorkRequestModal) {
            return;
        }
        if (procWorkRequestId) {
            procWorkRequestId.textContent = `#${HF.text(workRequestId)}`;
        }
        procWorkRequestModal.hidden = false;
    }

    function closeProcWorkRequestModal() {
        if (procWorkRequestModal) {
            procWorkRequestModal.hidden = true;
        }
    }

    function closeProcValueModal() {
        if (procValueModal) {
            procValueModal.hidden = true;
        }
    }

    async function pollInterfaceProperties() {
        if (!interfaceEditPanel) {
            return;
        }

        try {
            if (stateLabel) {
                stateLabel.textContent = "Polling";
            }

            const data = await HF.fetchJson("/api/traffic-counters");
            const ifaceName = interfaceEditPanel.dataset.interfaceEdit;
            const iface = data.interfaces.find((item) => item.name === ifaceName);
            if (!iface) {
                throw new Error(`Interface ${ifaceName} not found`);
            }

            renderInterfaceEditForm(iface);
            renderInterfaceEditAddresses(iface);

            if (stateLabel) {
                stateLabel.textContent = "Live";
            }
        } catch (error) {
            if (stateLabel) {
                stateLabel.textContent = "Offline";
            }
            interfaceEditPanel.insertAdjacentHTML("beforeend", `<div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>`);
        }
    }

    async function loadInterfaceEditProc() {
        if (!interfaceEditPanel || !interfaceEditProc) {
            return;
        }

        const ifaceName = interfaceEditPanel.dataset.interfaceEdit;

        try {
            const data = await HF.fetchJson("/api/proc");
            renderInterfaceEditProc((data.proc || []).filter((row) => row.iface_name === ifaceName));
        } catch (error) {
            interfaceEditProc.innerHTML = `
                <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
            `;
        }
    }

    function initializeProcValueEditor() {
        if (!interfaceEditPanel || !procValueModal || !procValueForm) {
            return;
        }

        document.addEventListener("click", (event) => {
            const editButton = event.target.closest("[data-proc-path]");
            if (editButton) {
                openProcValueModal(editButton.dataset.procPath, editButton.dataset.procValue);
                return;
            }

            if (event.target.id === "proc-value-close" || event.target.id === "proc-value-cancel" || event.target === procValueModal) {
                closeProcValueModal();
                return;
            }

            if (event.target.id === "proc-work-request-close" || event.target.id === "proc-work-request-cancel" || event.target === procWorkRequestModal) {
                closeProcWorkRequestModal();
            }
        });

        window.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                closeProcValueModal();
                closeProcWorkRequestModal();
            }
        });

        procValueForm.addEventListener("submit", async (event) => {
            event.preventDefault();

            const ifaceName = interfaceEditPanel.dataset.interfaceEdit;
            const procPath = procValuePath.value;
            const desiredValue = procValueCurrent.value.trim();

            if (procValueStatus) {
                procValueStatus.textContent = "saving";
            }

            try {
                const result = await HF.fetchJson("/api/proc/desired-value", {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        iface_name: ifaceName,
                        proc_path: procPath,
                        desired_value: desiredValue,
                    }),
                });
                closeProcValueModal();
                openProcWorkRequestModal(result.work_request);
                await loadInterfaceEditProc();
            } catch (error) {
                if (procValueStatus) {
                    procValueStatus.textContent = error.message;
                }
            }
        });
    }

    function initializeInterfaceEditor() {
        if (!interfaceEditPanel || !interfaceEditForm) {
            return;
        }

        interfaceEditForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const ifaceName = interfaceEditPanel.dataset.interfaceEdit;
            const formData = new FormData(interfaceEditForm);
            try {
                const result = await HF.fetchJson(`/api/interfaces/${encodeURIComponent(ifaceName)}`, {
                    method: "PUT",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        role: formData.get("role"),
                        protected: document.querySelector("#iface-edit-protected")?.value,
                        mtu: formData.get("mtu"),
                        description: formData.get("description"),
                    }),
                });
                openProcWorkRequestModal(result.work_request);
                if (stateLabel) {
                    stateLabel.textContent = "Work Request queued";
                }
            } catch (error) {
                if (stateLabel) {
                    stateLabel.textContent = error.message;
                }
            }
        });
    }

    initializeProcValueEditor();
    initializeInterfaceEditor();
    pollInterfaceProperties();
    loadInterfaceEditProc();
}());
