(function () {
    const themeStorageKey = "armfirewall-theme";
    const availableThemes = new Set(["default", "blue", "light", "red"]);

    function text(value) {
        return value === null || value === undefined || value === "" ? "-" : String(value);
    }

    function number(value) {
        return Number(value || 0);
    }

    function escapeHtml(value) {
        return text(value)
            .replaceAll("&", "&amp;")
            .replaceAll("<", "&lt;")
            .replaceAll(">", "&gt;")
            .replaceAll('"', "&quot;")
            .replaceAll("'", "&#039;");
    }

    async function fetchJson(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                "Accept": "application/json",
                ...(options.headers || {}),
            },
        });
        if (!response.ok) {
            let message = `HTTP ${response.status}`;
            try {
                const payload = await response.json();
                if (payload && payload.detail) {
                    message = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
                }
            } catch (_error) {
                message = response.statusText || message;
            }
            throw new Error(message);
        }
        return response.json();
    }

    function applyTheme(theme) {
        const selectedTheme = availableThemes.has(theme) ? theme : "default";
        document.documentElement.dataset.theme = selectedTheme;

        const themeSelect = document.querySelector("#theme-select");
        if (themeSelect) {
            themeSelect.value = selectedTheme;
        }
    }

    function initializeTheme() {
        const themeSelect = document.querySelector("#theme-select");
        const savedTheme = localStorage.getItem(themeStorageKey) || "default";
        applyTheme(savedTheme);

        if (themeSelect) {
            themeSelect.addEventListener("change", () => {
                localStorage.setItem(themeStorageKey, themeSelect.value);
                applyTheme(themeSelect.value);
            });
        }
    }

    function setMenuOpen(isOpen) {
        const menuToggle = document.querySelector(".menu-toggle");
        document.body.classList.toggle("menu-open", isOpen);

        if (menuToggle) {
            menuToggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
            menuToggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
        }
    }

    function initializeMobileMenu() {
        const menuToggle = document.querySelector(".menu-toggle");
        const menuBackdrop = document.querySelector("[data-menu-close]");
        const menuLinks = document.querySelectorAll(".sidebar .menu-link");

        if (menuToggle) {
            menuToggle.addEventListener("click", () => {
                setMenuOpen(!document.body.classList.contains("menu-open"));
            });
        }

        if (menuBackdrop) {
            menuBackdrop.addEventListener("click", () => setMenuOpen(false));
        }

        menuLinks.forEach((link) => {
            link.addEventListener("click", () => setMenuOpen(false));
        });

        window.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                setMenuOpen(false);
            }
        });

        window.addEventListener("resize", () => {
            if (window.innerWidth > 860) {
                setMenuOpen(false);
            }
        });
    }

    function initializeSidebarScrollMemory() {
        const sidebar = document.querySelector("#main-menu");
        const activeLink = sidebar ? sidebar.querySelector(".menu-link.active") : null;
        const storageKey = "armfw.sidebar.scrollTop";

        if (!sidebar) {
            return;
        }

        const saveScroll = () => {
            sessionStorage.setItem(storageKey, String(sidebar.scrollTop));
        };

        const savedScroll = Number(sessionStorage.getItem(storageKey) || "0");
        if (savedScroll > 0) {
            sidebar.scrollTop = savedScroll;
        } else if (activeLink) {
            activeLink.scrollIntoView({ block: "nearest" });
        }

        sidebar.addEventListener("scroll", saveScroll, { passive: true });
        sidebar.querySelectorAll("a[href]").forEach((link) => {
            link.addEventListener("click", saveScroll);
        });
        window.addEventListener("beforeunload", saveScroll);
    }

    function initializeArmTooltips() {
        const tooltip = document.querySelector(".arm-floating-tooltip") || document.createElement("div");
        tooltip.className = "arm-floating-tooltip";
        tooltip.hidden = true;
        if (!tooltip.parentElement) {
            document.body.appendChild(tooltip);
        }
        document.body.classList.add("arm-tooltips-enabled");

        let activeElement = null;

        function positionTooltip(element) {
            const value = element.dataset.tooltip || element.getAttribute("title") || "";
            if (!value) {
                tooltip.hidden = true;
                return;
            }

            tooltip.textContent = value;
            tooltip.hidden = false;
            tooltip.style.visibility = "hidden";
            tooltip.style.top = "0";
            tooltip.style.left = "0";

            const rect = element.getBoundingClientRect();
            const tipRect = tooltip.getBoundingClientRect();
            const margin = 12;
            const aboveTop = rect.top - tipRect.height - margin;
            const belowTop = rect.bottom + margin;
            const top = aboveTop >= margin ? aboveTop : Math.min(belowTop, window.innerHeight - tipRect.height - margin);
            const centeredLeft = rect.left + (rect.width / 2) - (tipRect.width / 2);
            const left = Math.min(Math.max(centeredLeft, margin), window.innerWidth - tipRect.width - margin);

            tooltip.style.top = `${Math.max(margin, top)}px`;
            tooltip.style.left = `${left}px`;
            tooltip.style.visibility = "visible";
        }

        function showTooltip(event) {
            const element = event.target.closest(".arm-tooltip[data-tooltip], .iface-tooltip[data-tooltip]");
            if (!element) {
                return;
            }
            if (element.hasAttribute("title")) {
                element.dataset.armTitle = element.getAttribute("title");
                element.removeAttribute("title");
            }
            activeElement = element;
            positionTooltip(element);
        }

        function restoreNativeTitle(element) {
            if (element && element.dataset.armTitle) {
                element.setAttribute("title", element.dataset.armTitle);
                delete element.dataset.armTitle;
            }
        }

        function hideTooltip(event) {
            if (!activeElement || (event.relatedTarget && activeElement.contains(event.relatedTarget))) {
                return;
            }
            restoreNativeTitle(activeElement);
            activeElement = null;
            tooltip.hidden = true;
        }

        document.addEventListener("mouseover", showTooltip);
        document.addEventListener("focusin", showTooltip);
        document.addEventListener("mouseout", hideTooltip);
        document.addEventListener("focusout", hideTooltip);
        window.addEventListener("scroll", () => {
            if (activeElement) {
                positionTooltip(activeElement);
            }
        }, true);
        window.addEventListener("resize", () => {
            if (activeElement) {
                positionTooltip(activeElement);
            }
        });
    }

    function renderSummary(summary) {
        const interfaces = document.querySelector("#summary-interfaces");
        const active = document.querySelector("#summary-active");

        if (interfaces) {
            interfaces.textContent = summary.interfaces;
        }

        if (active) {
            active.textContent = summary.active;
        }
    }

    function interfaceTooltip(iface) {
        const state = number(iface.is_actived) === 1 ? "UP" : "DOWN";
        const addresses = (iface.addresses || [])
            .map((address) => `${text(address.addr_family).toUpperCase()} ${text(address.addr)}/${text(address.prefixlen)}`)
            .join(", ");

        return [
            `Interface: ${text(iface.name).replace(/^if:/i, "")}`,
            `Role: ${text(iface.role || "UNKNOWN")}`,
            `Description: ${text(iface.description)}`,
            `MAC: ${text(iface.mac_address)}`,
            `MTU: ${text(iface.mtu)}`,
            `State: ${state}`,
            `Speed: ${number(iface.speed_mbps).toLocaleString()} Mb/s`,
            `Duplex: ${text(iface.duplex || "unknown")}`,
            addresses ? `Addresses: ${addresses}` : "Addresses: -",
        ].join("\n");
    }

    function renderCounterList(counterList, interfaces) {
        if (!counterList) {
            return;
        }

        if (!interfaces.length) {
            counterList.innerHTML = '<div class="terminal-empty"><span class="prompt">$</span><span>no counters</span></div>';
            return;
        }

        const maxRx = Math.max(1, ...interfaces.map((iface) => number(iface.rx_bytes)));
        const maxTx = Math.max(1, ...interfaces.map((iface) => number(iface.tx_bytes)));

        counterList.innerHTML = interfaces.map((iface) => {
            const rxWidth = Math.max(2, Math.round((number(iface.rx_bytes) / maxRx) * 100));
            const txWidth = Math.max(2, Math.round((number(iface.tx_bytes) / maxTx) * 100));
            const errorCount = number(iface.rx_errors) + number(iface.tx_errors) + number(iface.rx_dropped) + number(iface.tx_dropped);

            const role = text(iface.role || "UNKNOWN");
            const ifaceName = text(iface.name).replace(/^if:/i, "");
            const ifaceLabel = `${ifaceName} (${role})`;
            const tooltip = interfaceTooltip(iface);

            return `
                <div class="counter-row">
                    <div class="counter-name"><span class="iface-tooltip" tabindex="0" title="${escapeHtml(tooltip)}" data-tooltip="${escapeHtml(tooltip)}">${escapeHtml(ifaceLabel)}</span></div>
                    <div class="bar-item">
                        <div class="bar-label">
                            <span>RX ${number(iface.rx_packets).toLocaleString()} pkts</span>
                            <span>${escapeHtml(iface.rx_label)}</span>
                        </div>
                        <div class="bar-track"><div class="bar-fill" style="width:${rxWidth}%"></div></div>
                    </div>
                    <div class="bar-item">
                        <div class="bar-label">
                            <span>TX ${number(iface.tx_packets).toLocaleString()} pkts</span>
                            <span>${escapeHtml(iface.tx_label)} / err ${errorCount.toLocaleString()}</span>
                        </div>
                        <div class="bar-track"><div class="bar-fill tx" style="width:${txWidth}%"></div></div>
                    </div>
                </div>
            `;
        }).join("");
    }

    window.HF = {
        escapeHtml,
        fetchJson,
        number,
        renderCounterList,
        renderSummary,
        text,
    };

    initializeTheme();
    initializeMobileMenu();
    initializeSidebarScrollMemory();
    initializeArmTooltips();
}());
