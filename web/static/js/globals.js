(function () {
    const themeStorageKey = "homefirewall-theme";
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
            throw new Error(`HTTP ${response.status}`);
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

            return `
                <div class="counter-row">
                    <div class="counter-name">${escapeHtml(ifaceLabel)}</div>
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
}());
