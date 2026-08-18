(() => {
    const state = document.getElementById("monitoring-refresh-state");
    const modal = document.getElementById("graph-modal");
    const modalTitle = document.getElementById("graph-modal-title");
    const modalImage = document.getElementById("graph-modal-image");
    const targetSelect = document.getElementById("latency-target-select");
    const targetsBody = document.getElementById("latency-targets-body");
    const targetCount = document.getElementById("latency-target-count");
    const editModal = document.getElementById("latency-edit-modal");
    const editForm = document.getElementById("latency-edit-form");
    const editTitle = document.getElementById("latency-edit-title");
    const editStatus = document.getElementById("latency-edit-status");
    const deleteModal = document.getElementById("latency-delete-modal");
    const deleteMessage = document.getElementById("latency-delete-message");
    const deleteStatus = document.getElementById("latency-delete-status");
    const deleteConfirm = document.getElementById("latency-delete-confirm");
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
    let currentPeriod = localStorage.getItem("armfw.monitoring.latency.period") || "daily";
    let currentTarget = localStorage.getItem("armfw.monitoring.latency.target") || "";
    let lastGraphs = [];
    let lastLatencyTargets = [];
    let activeModalGraphId = "";
    let pendingDeleteTargetId = "";
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

    function selectedPeriod(graph) {
        const periods = graph.periods || {};
        return periods[currentPeriod] || periods.daily || graph;
    }

    function latestUpdatedLabel() {
        let latest = null;
        lastGraphs.forEach((graph) => {
            if (graph.latency_target_name !== currentTarget) {
                return;
            }
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

    function setActivePeriodButton() {
        periodButtons.forEach((button) => {
            button.classList.toggle("active", button.dataset.periodButton === currentPeriod);
        });
    }

    function initializeTargetSelection(targets = []) {
        if (!targetSelect) {
            return;
        }
        if (targets.length) {
            targetSelect.replaceChildren(
                ...targets.map((target) => {
                    const option = document.createElement("option");
                    option.value = target.safe_name;
                    option.textContent = target.label;
                    return option;
                })
            );
        }
        const values = Array.from(targetSelect.options).map((option) => option.value);
        if (!currentTarget || !values.includes(currentTarget)) {
            currentTarget = values[0] || "";
        }
        targetSelect.value = currentTarget;
    }

    function setVisibleTarget() {
        cards.forEach((card) => {
            const visible = !currentTarget || card.dataset.latencyTarget === currentTarget;
            card.hidden = !visible;
        });
    }

    function renderTargetRows(targets = []) {
        lastLatencyTargets = targets;
        if (targetCount) {
            targetCount.textContent = `targets=${targets.length}`;
        }
        if (!targetsBody) {
            return;
        }
        if (!targets.length) {
            targetsBody.innerHTML = '<tr><td colspan="7" class="empty-state">No latency targets configured</td></tr>';
            return;
        }
        targetsBody.innerHTML = targets.map((target) => `
            <tr>
                <td><span class="iface-tooltip" tabindex="0" title="${HF.escapeHtml(target.interface_tooltip || "")}" data-tooltip="${HF.escapeHtml(target.interface_tooltip || "")}">${HF.escapeHtml(target.iface || "-")}</span></td>
                <td>${HF.escapeHtml(target.target || "-")}</td>
                <td>${HF.escapeHtml(String(target.count || "-"))}</td>
                <td>${HF.escapeHtml(String(target.timeout || "-"))}s</td>
                <td>${target.enabled ? "enabled" : "disabled"}</td>
                <td>${HF.escapeHtml(target.updated_at || "-")}</td>
                <td>
                    <button class="text-button compact" type="button" data-latency-edit="${HF.escapeHtml(String(target.id))}">Edit</button>
                    <button class="text-button compact" type="button" data-latency-toggle="${HF.escapeHtml(String(target.id))}" data-enabled="${target.enabled ? "1" : "0"}">${target.enabled ? "Disable" : "Enable"}</button>
                    <button class="text-button compact" type="button" data-latency-delete="${HF.escapeHtml(String(target.id))}">Delete</button>
                </td>
            </tr>
        `).join("");
    }

    async function latencyRequest(url, options = {}) {
        const response = await fetch(url, {
            ...options,
            headers: {
                "Accept": "application/json",
                ...(options.headers || {}),
            },
        });
        if (!response.ok) {
            let detail = `HTTP ${response.status}`;
            try {
                const body = await response.json();
                detail = body.detail || detail;
            } catch (error) {
                detail = `HTTP ${response.status}`;
            }
            throw new Error(detail);
        }
        return response.json();
    }

    function targetById(targetId) {
        return lastLatencyTargets.find((target) => String(target.id) === String(targetId));
    }

    function openAddModal() {
        if (!editModal || !editForm) {
            return;
        }
        editForm.elements.id.value = "";
        editForm.elements.iface.value = "";
        editForm.elements.target.value = "";
        editForm.elements.count.value = 3;
        editForm.elements.timeout.value = 3;
        if (editTitle) {
            editTitle.textContent = "Add latency target";
        }
        if (editStatus) {
            editStatus.textContent = "";
        }
        editModal.hidden = false;
        editForm.elements.target.focus();
    }

    function openEditModal(targetId) {
        const target = targetById(targetId);
        if (!target || !editModal || !editForm) {
            return;
        }
        editForm.elements.id.value = target.id;
        editForm.elements.iface.value = target.iface || "";
        editForm.elements.target.value = target.target || "";
        editForm.elements.count.value = target.count || 3;
        editForm.elements.timeout.value = target.timeout || 3;
        if (editTitle) {
            editTitle.textContent = "Edit latency target";
        }
        if (editStatus) {
            editStatus.textContent = "";
        }
        editModal.hidden = false;
        editForm.elements.target.focus();
    }

    function closeEditModal() {
        if (editModal) {
            editModal.hidden = true;
        }
    }

    function openDeleteModal(targetId) {
        const target = targetById(targetId);
        if (!target || !deleteModal) {
            return;
        }
        pendingDeleteTargetId = String(target.id);
        if (deleteMessage) {
            deleteMessage.textContent = `delete ${target.target} on ${target.iface}?`;
        }
        if (deleteStatus) {
            deleteStatus.textContent = "";
        }
        deleteModal.hidden = false;
    }

    function closeDeleteModal() {
        if (deleteModal) {
            deleteModal.hidden = true;
        }
        pendingDeleteTargetId = "";
    }

    async function toggleTarget(targetId, enabled) {
        await latencyRequest(`/api/monitoring/latency/${targetId}/enabled`, {
            method: "PUT",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({enabled}),
        });
        await refreshGraphs();
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

    function updateModalImage(graph) {
        const period = selectedPeriod(graph);
        if (!modalImage || !modalTitle || !period.exists) {
            return;
        }
        modalTitle.textContent = `${graph.title} / ${period.label || periodLabels[currentPeriod] || "Daily"}`;
        modalImage.src = `${period.image_url}?v=${period.updated_at || refreshToken}&r=${refreshToken}`;
        modalImage.alt = `${graph.title} ${period.label || "Daily"} graph`;
    }

    function updateAllGraphs() {
        setActivePeriodButton();
        setVisibleTarget();
        lastGraphs.forEach(updateGraph);
        if (activeModalGraphId) {
            const graph = lastGraphs.find((item) => item.id === activeModalGraphId);
            if (graph) {
                updateModalImage(graph);
            }
        }
        setRefreshState("Live", latestUpdatedLabel() || "-");
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
            const response = await fetch("/api/monitoring/latency", { cache: "no-store", credentials: "same-origin" });
            if (!response.ok) {
                if (response.status === 401) { window.location.href = "/login"; return; }
                if (response.status === 403) { window.location.href = "/login/change-password"; return; }
                throw new Error("HTTP " + response.status);
            }
            const data = await response.json();
            refreshToken = Date.now();
            lastGraphs = data.graphs || [];
            initializeTargetSelection(data.targets || []);
            renderTargetRows(data.latency_targets || []);
            updateAllGraphs();
        } catch (error) {
            setRefreshState("Error " + (error.message || "refresh failed"));
        }
    }

    periodButtons.forEach((button) => {
        button.addEventListener("click", () => {
            currentPeriod = button.dataset.periodButton || "daily";
            localStorage.setItem("armfw.monitoring.latency.period", currentPeriod);
            updateAllGraphs();
        });
    });

    if (targetSelect) {
        targetSelect.addEventListener("change", () => {
            currentTarget = targetSelect.value;
            localStorage.setItem("armfw.monitoring.latency.target", currentTarget);
            updateAllGraphs();
        });
    }

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

        const editButton = event.target.closest("[data-latency-edit]");
        if (editButton) {
            openEditModal(editButton.dataset.latencyEdit);
            return;
        }

        if (event.target.closest("[data-latency-add]")) {
            openAddModal();
            return;
        }

        const toggleButton = event.target.closest("[data-latency-toggle]");
        if (toggleButton) {
            toggleTarget(toggleButton.dataset.latencyToggle, toggleButton.dataset.enabled !== "1").catch(() => {
                setRefreshState("Error " + (error.message || "refresh failed"));
            });
            return;
        }

        const deleteButton = event.target.closest("[data-latency-delete]");
        if (deleteButton) {
            openDeleteModal(deleteButton.dataset.latencyDelete);
            return;
        }

        if (event.target.closest("[data-latency-modal-close]")) {
            closeEditModal();
            return;
        }

        if (event.target.closest("[data-latency-delete-close]")) {
            closeDeleteModal();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeModal();
            closeEditModal();
            closeDeleteModal();
        }
    });

    if (editForm) {
        editForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            if (editStatus) {
                editStatus.textContent = "saving";
            }
            try {
                const targetId = editForm.elements.id.value;
                await latencyRequest(targetId ? `/api/monitoring/latency/${targetId}` : "/api/monitoring/latency", {
                    method: targetId ? "PUT" : "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({
                        iface: editForm.elements.iface.value.trim(),
                        target: editForm.elements.target.value.trim(),
                        count: Number(editForm.elements.count.value || 3),
                        timeout: Number(editForm.elements.timeout.value || 3),
                    }),
                });
                closeEditModal();
                await refreshGraphs();
            } catch (error) {
                if (editStatus) {
                    editStatus.textContent = error.message;
                }
            }
        });
    }

    if (deleteConfirm) {
        deleteConfirm.addEventListener("click", async () => {
            if (!pendingDeleteTargetId) {
                return;
            }
            if (deleteStatus) {
                deleteStatus.textContent = "deleting";
            }
            try {
                await latencyRequest(`/api/monitoring/latency/${pendingDeleteTargetId}`, {method: "DELETE"});
                closeDeleteModal();
                await refreshGraphs();
            } catch (error) {
                if (deleteStatus) {
                    deleteStatus.textContent = error.message;
                }
            }
        });
    }

    initializeTargetSelection();
    renderTargetRows();
    setActivePeriodButton();
    setVisibleTarget();
    setState("Loading");
    refreshGraphs();
    window.setInterval(refreshGraphs, 10000);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            refreshGraphs();
        }
    });
    window.addEventListener("pageshow", refreshGraphs);
})();
