(() => {
    const state = document.getElementById("monitoring-refresh-state");
    const modal = document.getElementById("graph-modal");
    const modalTitle = document.getElementById("graph-modal-title");
    const modalImage = document.getElementById("graph-modal-image");
    const periodButtons = Array.from(document.querySelectorAll("[data-period-button]"));
    const cards = new Map(
        Array.from(document.querySelectorAll("[data-graph-card]")).map((card) => [card.dataset.graphId, card])
    );
    const periodLabels = {
        daily: "Daily",
        weekly: "Weekly",
        monthly: "Monthly",
        yearly: "Yearly",
    };
    let currentPeriod = localStorage.getItem("armfw.monitoring.period") || "daily";
    let lastGraphs = [];
    let activeModalGraphId = "";
    let refreshToken = Date.now();

    function setState(value) {
        if (state) {
            state.textContent = value;
        }
    }

    function setRefreshState(value, updated = "") {
        if (!state) {
            return;
        }
        if (updated) {
            state.innerHTML = `${HF.escapeHtml(value)} / <span class="refresh-state-label">updated=</span>${HF.escapeHtml(updated)}`;
            return;
        }
        state.textContent = value;
    }

    function latestUpdatedLabel() {
        let latest = null;
        lastGraphs.forEach((graph) => {
            const period = selectedPeriod(graph);
            if (!period || !period.updated_at || !period.updated_label) {
                return;
            }
            if (!latest || Number(period.updated_at) > Number(latest.updated_at)) {
                latest = period;
            }
        });
        return latest ? latest.updated_label : "";
    }

    function formatUpdated(value) {
        if (!value) {
            return "missing";
        }
        return "ready";
    }

    function selectedPeriod(graph) {
        const periods = graph.periods || {};
        return periods[currentPeriod] || periods.daily || graph;
    }

    function setActivePeriodButton() {
        periodButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.periodButton === currentPeriod);
        });
    }

    function updateGraph(graph) {
        const card = cards.get(graph.id);
        if (!card) {
            return;
        }
        const period = selectedPeriod(graph);
        const body = card.querySelector(".monitoring-graph-body");
        const updated = card.querySelector("[data-graph-updated]");
        const periodLabel = card.querySelector("[data-graph-period-label]");
        if (periodLabel) {
            periodLabel.textContent = `${period.label || periodLabels[currentPeriod] || "Daily"} / ${graph.rrd}`;
        }
        if (updated) {
            updated.textContent = formatUpdated(period.updated_at);
        }
        if (!body || !period.exists) {
            return;
        }
        let image = card.querySelector("[data-graph-image]");
        if (!image) {
            const button = document.createElement("button");
            button.className = "monitoring-graph-zoom";
            button.type = "button";
            button.dataset.graphZoom = "true";
            image = document.createElement("img");
            image.alt = `${graph.title} graph`;
            image.dataset.graphImage = "true";
            button.appendChild(image);
            body.replaceChildren(button);
        }
        image.dataset.graphSrc = period.image_url;
        image.src = `${period.image_url}?v=${period.updated_at || refreshToken}&r=${refreshToken}`;
    }

    function updateAllGraphs() {
        setActivePeriodButton();
        lastGraphs.forEach(updateGraph);
        if (activeModalGraphId) {
            const graph = lastGraphs.find((item) => item.id === activeModalGraphId);
            if (graph) {
                updateModalImage(graph);
            }
        }
        setRefreshState("Live", latestUpdatedLabel() || "-");
    }

    function updateModalImage(graph) {
        const period = selectedPeriod(graph);
        if (!modalImage || !modalTitle || !period.exists) {
            return;
        }
        modalTitle.textContent = `${graph.title} / ${period.label || periodLabels[currentPeriod] || "Daily"}`;
        modalImage.src = `${period.image_url}?v=${period.updated_at || refreshToken}&r=${refreshToken}`;
        modalImage.alt = `${graph.title} ${period.label || "Daily"} graph`;
    }

    function openModal(graphId) {
        const graph = lastGraphs.find((item) => item.id === graphId);
        if (!modal || !graph) {
            return;
        }
        activeModalGraphId = graphId;
        updateModalImage(graph);
        modal.hidden = false;
        document.body.classList.add("graph-modal-open");
    }

    function closeModal() {
        if (!modal) {
            return;
        }
        modal.hidden = true;
        document.body.classList.remove("graph-modal-open");
        activeModalGraphId = "";
    }

    async function refreshGraphs() {
        try {
            const response = await fetch("/api/monitoring/cpu-mem", { cache: "no-store" });
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const data = await response.json();
            refreshToken = Date.now();
            lastGraphs = data.graphs || [];
            updateAllGraphs();
        } catch (error) {
            setRefreshState("Error");
        }
    }

    periodButtons.forEach((button) => {
        button.addEventListener("click", () => {
            currentPeriod = button.dataset.periodButton || "daily";
            localStorage.setItem("armfw.monitoring.period", currentPeriod);
            updateAllGraphs();
        });
    });

    document.addEventListener("click", (event) => {
        const zoomButton = event.target.closest("[data-graph-zoom]");
        if (zoomButton) {
            const card = zoomButton.closest("[data-graph-card]");
            if (card) {
                openModal(card.dataset.graphId);
            }
            return;
        }
        if (event.target.closest("[data-graph-modal-close]")) {
            closeModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeModal();
        }
    });

    setActivePeriodButton();
    setState("Loading");
    refreshGraphs();
    window.setInterval(refreshGraphs, 10000);
})();
