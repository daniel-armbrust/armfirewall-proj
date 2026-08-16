(function () {
    const form = document.querySelector("#adguard-form");
    const state = document.querySelector("#adguard-state");
    const status = document.querySelector("#adguard-status");
    let current = null;

    function setValue(name, value) {
        const field = form.elements.namedItem(name);
        if (field) field.value = Array.isArray(value) ? value.join("\n") : String(value ?? "");
    }
    function setState(value) { if (state) state.textContent = value; }
    function showError(message) { status.textContent = message; status.classList.add("error"); status.hidden = false; }
    function clearStatus() { status.hidden = true; status.classList.remove("error"); }
    function values() {
        const payload = {};
        ["protection_enabled", "filtering_enabled", "safe_browsing_enabled", "parental_enabled", "safe_search_enabled", "query_log_enabled"].forEach((name) => { payload[name] = form.elements.namedItem(name).value === "1"; });
        ["filter_update_interval_hours", "query_log_retention_hours", "statistics_interval_hours", "dns_port", "web_port"].forEach((name) => { payload[name] = form.elements.namedItem(name).value; });
        ["dns_bind_host", "web_bind_host"].forEach((name) => { payload[name] = form.elements.namedItem(name).value.trim(); });
        ["upstream_dns_servers", "fallback_dns_servers", "bootstrap_dns_servers"].forEach((name) => { payload[name] = form.elements.namedItem(name).value.split(/\s+/).filter(Boolean); });
        return payload;
    }
    function render(data) {
        current = data;
        const settings = data.settings;
        Object.keys(settings).forEach((key) => { if (form.elements.namedItem(key)) setValue(key, settings[key]); });
        document.querySelector("#adguard-service").textContent = data.service.state || "-";
        document.querySelector("#adguard-protection").textContent = settings.protection_enabled ? "enabled" : "disabled";
        document.querySelector("#adguard-filters-count").textContent = data.filters.length;
        document.querySelector("#adguard-pending").textContent = settings.pending_apply ? "yes" : "no";
        document.querySelector("#adguard-filters").innerHTML = data.filters.length ? data.filters.map((filter) => `<tr><td>${HF.escapeHtml(filter.name)}</td><td>${HF.escapeHtml(filter.source_url)}</td><td>${filter.enabled ? "enabled" : "disabled"}</td><td><button class="text-button compact danger" type="button" data-filter-id="${filter.id}">Remove</button></td></tr>`).join("") : `<tr><td colspan="4"><div class="terminal-empty"><span class="prompt">$</span><span>no filter sources configured</span></div></td></tr>`;
        setState("Live");
    }
    async function load() { try { render(await HF.fetchJson("/api/services/adguardhome")); } catch (error) { setState("Offline"); showError(error.message); } }
    form.addEventListener("submit", async (event) => { event.preventDefault(); clearStatus(); try { render(await HF.fetchJson("/api/services/adguardhome", {method: "PUT", headers: {"Content-Type": "application/json"}, body: JSON.stringify(values())})); } catch (error) { showError(error.message); } });
    document.querySelector("#adguard-filter-add").addEventListener("click", async () => { try { const name = document.querySelector("#adguard-filter-name").value.trim(); const source_url = document.querySelector("#adguard-filter-url").value.trim(); render(await HF.fetchJson("/api/services/adguardhome/filters", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({name, source_url})})); document.querySelector("#adguard-filter-name").value = ""; document.querySelector("#adguard-filter-url").value = ""; } catch (error) { showError(error.message); } });
    document.addEventListener("click", async (event) => { const button = event.target.closest("[data-filter-id]"); if (!button) return; try { render(await HF.fetchJson(`/api/services/adguardhome/filters/${button.dataset.filterId}`, {method: "DELETE"})); } catch (error) { showError(error.message); } });
    load();
}());
