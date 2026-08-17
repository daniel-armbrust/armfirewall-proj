(function () {
    const stateLabel = document.querySelector("#work-requests-state");
    const body = document.querySelector("#work-requests-body");
    const count = document.querySelector("#work-requests-count");
    const pageSize = document.querySelector("#work-requests-page-size");
    const previousButton = document.querySelector("#work-requests-previous");
    const nextButton = document.querySelector("#work-requests-next");
    const paginationLabel = document.querySelector("#work-requests-pagination");
    const POLL_MS = 5000;
    let loading = false;
    let currentPage = 1;

    function statusClass(status) {
        if (status === "success") return "up";
        if (status === "failed") return "down";
        return "disabled";
    }

    function setMetric(id, value) {
        const element = document.querySelector(id);
        if (element) element.textContent = HF.text(value);
    }

    function render(data) {
        const requests = data.requests || [];
        const summary = data.summary || {};
        const pagination = data.pagination || {};
        setMetric("#work-requests-total", pagination.total || 0);
        setMetric("#work-requests-queued", summary.queue || 0);
        setMetric("#work-requests-running", summary.running || 0);
        setMetric("#work-requests-failed", summary.failed || 0);
        if (count) count.textContent = `requests=${requests.length}`;
        if (stateLabel) stateLabel.textContent = "Ready";
        const page = pagination.page || 1;
        const pageSizeValue = pagination.page_size || Number(pageSize?.value || 25);
        const total = pagination.total || 0;
        const firstItem = total ? ((page - 1) * pageSizeValue) + 1 : 0;
        const lastItem = total ? Math.min(page * pageSizeValue, total) : 0;
        if (paginationLabel) paginationLabel.textContent = `Page ${page} of ${pagination.pages || 1} (${firstItem} - ${lastItem} of ${total} total items)`;
        if (previousButton) previousButton.disabled = (pagination.page || 1) <= 1;
        if (nextButton) nextButton.disabled = (pagination.page || 1) >= (pagination.pages || 1);

        if (!requests.length) {
            body.innerHTML = '<tr><td colspan="8"><div class="terminal-empty"><span class="prompt">$</span><span>no work requests</span></div></td></tr>';
            return;
        }

        body.innerHTML = requests.map((request) => `
            <tr>
                <td>${HF.escapeHtml(request.id)}</td>
                <td><span class="status ${statusClass(request.status)}">${HF.escapeHtml(request.status)}</span></td>
                <td>${HF.escapeHtml(request.category_name)}</td>
                <td>${HF.escapeHtml(request.action_name)}</td>
                <td>${HF.escapeHtml(request.source)}</td>
                <td>${HF.escapeHtml(request.priority)}</td>
                <td>${HF.escapeHtml(request.updated_at)}</td>
                <td>${HF.escapeHtml(request.error_message || "")}</td>
            </tr>
        `).join("");
    }

    async function load() {
        if (loading) return;
        loading = true;
        try {
            const size = Number(pageSize?.value || 25);
            render(await HF.fetchJson(`/api/work-requests?limit=${size}&page=${currentPage}`));
        } catch (error) {
            if (stateLabel) stateLabel.textContent = "Error";
            body.innerHTML = `<tr><td colspan="8"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td></tr>`;
        } finally {
            loading = false;
        }
    }

    function scrollToTop() {
        document.querySelector("#main-content")?.scrollTo({top: 0, behavior: "smooth"});
        window.scrollTo({top: 0, behavior: "smooth"});
    }

    load();
    window.setInterval(load, POLL_MS);
    pageSize?.addEventListener("change", () => { currentPage = 1; load(); });
    previousButton?.addEventListener("click", () => { if (currentPage > 1) { currentPage -= 1; scrollToTop(); load(); } });
    nextButton?.addEventListener("click", () => { currentPage += 1; scrollToTop(); load(); });
}());
