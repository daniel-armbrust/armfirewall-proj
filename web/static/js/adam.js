(function () {
    const state = document.getElementById("adam-state");
    const datasetToggle = document.getElementById("adam-dataset-toggle");
    const datasetPanel = document.getElementById("adam-dataset-panel");
    const fileInput = document.getElementById("adam-dataset-input");
    const importButton = document.getElementById("adam-dataset-import");
    const status = document.getElementById("adam-dataset-status");
    const fileLabel = document.getElementById("adam-dataset-file");
    const rowsLabel = document.getElementById("adam-dataset-rows");
    const intentionsLabel = document.getElementById("adam-dataset-intentions");
    const updatedLabel = document.getElementById("adam-dataset-updated");
    const maximumSize = 5 * 1024 * 1024;

    if (!datasetToggle || !datasetPanel || !fileInput || !importButton) {
        return;
    }

    function setDatasetPanelOpen(open) {
        datasetPanel.hidden = !open;
        datasetToggle.classList.toggle("active", open);
        datasetToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function setState(value) {
        if (state) {
            state.textContent = value;
        }
    }

    function setStatus(message, isError = false) {
        if (!status) {
            return;
        }
        status.textContent = message || "";
        status.classList.toggle("error", Boolean(isError));
    }

    function setUploading(uploading) {
        fileInput.disabled = uploading;
        importButton.disabled = uploading;
        importButton.textContent = uploading
            ? "Uploading..."
            : "Import training CSV";
    }

    function renderDataset(dataset) {
        const available = Boolean(dataset);
        fileLabel.textContent = available ? dataset.file_name : "None";
        rowsLabel.textContent = available ? String(dataset.rows) : "0";
        intentionsLabel.textContent = available ? String(dataset.intentions) : "0";
        updatedLabel.textContent = available
            ? new Date(dataset.updated_at).toLocaleString("en-US")
            : "-";
        setState(available ? "Dataset available" : "Waiting for dataset");
    }

    async function parseResponse(response) {
        const text = await response.text();
        if (!text) {
            return {};
        }
        try {
            return JSON.parse(text);
        } catch (error) {
            return { detail: text.trim() || "Invalid server response." };
        }
    }

    function handleAuthentication(response) {
        if (response.status === 401) {
            window.location.href = "/login";
            return true;
        }
        if (response.status === 403) {
            window.location.href = "/login/change-password";
            return true;
        }
        return false;
    }

    async function loadDataset() {
        try {
            const response = await fetch("/api/adam/training-dataset", {
                cache: "no-store",
                credentials: "same-origin",
                headers: { "Accept": "application/json" },
            });
            if (handleAuthentication(response)) {
                return;
            }
            const payload = await parseResponse(response);
            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }
            renderDataset(payload.dataset || null);
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
        }
    }

    async function uploadDataset(file) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
            setStatus("Select a file with a .csv extension.", true);
            return;
        }
        if (!file.size) {
            setStatus("The selected file is empty.", true);
            return;
        }
        if (file.size > maximumSize) {
            setStatus("The selected file exceeds the 5 MB limit.", true);
            return;
        }

        setUploading(true);
        setState("Uploading");
        setStatus("");
        try {
            const response = await fetch("/api/adam/training-dataset", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "text/csv",
                    "X-File-Name": encodeURIComponent(file.name),
                },
                body: file,
            });
            if (handleAuthentication(response)) {
                return;
            }
            const payload = await parseResponse(response);
            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }
            renderDataset(payload.dataset);
            setStatus(payload.message || "Dataset imported successfully.");
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
        } finally {
            setUploading(false);
            fileInput.value = "";
        }
    }

    datasetToggle.addEventListener("click", () => {
        setDatasetPanelOpen(datasetPanel.hidden);
    });

    importButton.addEventListener("click", () => fileInput.click());
    fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (file) {
            uploadDataset(file);
        }
    });

    loadDataset();
})();
