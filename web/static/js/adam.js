(function () {
    const state = document.getElementById("adam-state");
    const datasetToggle = document.getElementById("adam-dataset-toggle");
    const datasetPanel = document.getElementById("adam-dataset-panel");
    const workRequestsToggle = document.getElementById("adam-work-requests-toggle");
    const workRequestsPanel = document.getElementById("adam-work-requests-panel");
    const workRequestsBody = document.getElementById("adam-work-requests-body");
    const workRequestsCount = document.getElementById("adam-work-requests-count");
    const datasetCategory = document.getElementById("adam-dataset-category");
    const trainingInput = document.getElementById("adam-training-dataset-input");
    const testingInput = document.getElementById("adam-testing-dataset-input");
    const trainingImport = document.getElementById("adam-training-dataset-import");
    const testingImport = document.getElementById("adam-testing-dataset-import");
    const trainingName = document.getElementById("adam-training-dataset-name");
    const testingName = document.getElementById("adam-testing-dataset-name");
    const trainingModel = document.getElementById("adam-training-model");
    const status = document.getElementById("adam-dataset-status");
    const fileLabel = document.getElementById("adam-dataset-file");
    const rowsLabel = document.getElementById("adam-dataset-rows");
    const intentionsLabel = document.getElementById("adam-dataset-intentions");
    const updatedLabel = document.getElementById("adam-dataset-updated");
    const workRequestRefreshMs = 3000;
    let activeDataset = null;
    let uploadInProgress = false;
    let trainingInProgress = false;
    let workRequestsLoading = false;

    if (!datasetToggle || !datasetPanel || !workRequestsToggle || !workRequestsPanel
            || !datasetCategory || !trainingInput || !testingInput || !trainingImport || !testingImport
            || !trainingName || !testingName || !trainingModel) {
        return;
    }

    function setActiveView(view) {
        const datasetSelected = view === "dataset";
        datasetPanel.hidden = !datasetSelected;
        workRequestsPanel.hidden = datasetSelected;
        datasetToggle.classList.toggle("active", datasetSelected);
        workRequestsToggle.classList.toggle("active", !datasetSelected);
        datasetToggle.setAttribute("aria-expanded", datasetSelected ? "true" : "false");

        if (!datasetSelected) {
            loadWorkRequests({force: true});
        }
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

    function syncControls() {
        const training = activeDataset && activeDataset.training;
        const testing = activeDataset && activeDataset.testing;
        const editable = !activeDataset || activeDataset.status === "uploaded";
        const busy = uploadInProgress || trainingInProgress;

        trainingInput.disabled = busy;
        datasetCategory.disabled = busy;
        testingInput.disabled = busy || !training || !editable;
        trainingImport.disabled = busy;
        testingImport.disabled = busy || !training || !editable;
        trainingModel.disabled = busy || !training || !testing || !editable;
    }

    function renderDataset(dataset) {
        activeDataset = dataset || null;
        const training = activeDataset && activeDataset.training;
        const testing = activeDataset && activeDataset.testing;

        trainingName.value = training ? training.file_name : "";
        testingName.value = testing ? testing.file_name : "";
        fileLabel.textContent = training ? training.file_name : "-";
        rowsLabel.textContent = training ? String(training.rows) : "0";
        intentionsLabel.textContent = activeDataset
            ? String(activeDataset.intentions || 0)
            : "0";
        updatedLabel.textContent = activeDataset
            ? new Date(activeDataset.updated_at).toLocaleString("en-US")
            : "-";

        if (!activeDataset) {
            setState("Waiting for training dataset");
        } else if (activeDataset.status === "queue") {
            setState("Training queued");
        } else if (activeDataset.status === "running") {
            setState("Training model");
        } else if (activeDataset.status === "success") {
            setState("Model available");
        } else if (activeDataset.status === "failed") {
            setState("Training failed");
        } else if (!testing) {
            setState("Waiting for testing dataset");
        } else {
            setState("Ready for training");
        }

        syncControls();
    }

    async function parseResponse(response) {
        const text = await response.text();

        if (!text) {
            return {};
        }

        try {
            return JSON.parse(text);
        } catch (error) {
            return {detail: text.trim() || "Invalid server response."};
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
            const category = encodeURIComponent(datasetCategory.value);
            const response = await fetch(`/api/adam/dataset?dataset_category=${category}`, {
                cache: "no-store",
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
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

    function validateFile(file) {
        if (!file.name.toLowerCase().endsWith(".csv")) {
            setStatus("Select a file with a .csv extension.", true);
            return false;
        }

        if (!file.size) {
            setStatus("The selected file is empty.", true);
            return false;
        }

        return true;
    }

    async function uploadDataset(file, datasetType) {
        if (!validateFile(file)) {
            return;
        }

        uploadInProgress = true;
        syncControls();
        setState(`Uploading ${datasetType} dataset`);
        setStatus("");

        const button = datasetType === "training" ? trainingImport : testingImport;
        const defaultLabel = datasetType === "training"
            ? "Load Training Dataset"
            : "Load Test Dataset";
        button.textContent = "Uploading...";

        try {
            const response = await fetch(
                `/api/adam/dataset?dataset_type=${encodeURIComponent(datasetType)}&dataset_category=${encodeURIComponent(datasetCategory.value)}`,
                {
                    method: "POST",
                    credentials: "same-origin",
                    headers: {
                        "Accept": "application/json",
                        "Content-Type": "text/csv",
                        "X-File-Name": encodeURIComponent(file.name),
                    },
                    body: file,
                },
            );

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);

            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }

            renderDataset(payload.dataset);
            setStatus(payload.message || "Dataset loaded successfully.");
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
        } finally {
            uploadInProgress = false;
            button.textContent = defaultLabel;
            trainingInput.value = "";
            testingInput.value = "";
            syncControls();
        }
    }

    async function queueTraining() {
        trainingInProgress = true;
        syncControls();
        trainingModel.textContent = "Queueing...";
        setState("Queueing training");
        setStatus("");

        try {
            const category = encodeURIComponent(datasetCategory.value);
            const response = await fetch(`/api/adam/training?dataset_category=${category}`, {
                method: "POST",
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
            });

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);

            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }

            renderDataset(payload.dataset);
            setStatus(payload.message || "Training work request queued successfully.");
            setActiveView("work-requests");
        } catch (error) {
            setState("Error");
            setStatus(error.message, true);
            await loadDataset();
        } finally {
            trainingInProgress = false;
            trainingModel.textContent = "Train Model";
            syncControls();
        }
    }

    function renderWorkRequests(payload) {
        const requests = payload.requests || [];
        workRequestsCount.textContent = `requests=${requests.length}`;

        if (!requests.length) {
            workRequestsBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>no ADAM work requests</span></div></td>
                </tr>
            `;
            return;
        }

        workRequestsBody.innerHTML = requests.map((workRequest) => {
            const failed = workRequest.status === "failed";
            const statusClass = failed
                ? "down"
                : workRequest.status === "success" ? "up" : "disabled";

            return `
                <tr>
                    <td>${HF.escapeHtml(workRequest.id)}</td>
                    <td><span class="status ${statusClass}">${HF.escapeHtml(workRequest.status)}</span></td>
                    <td>${HF.escapeHtml(workRequest.action_name || "-")}</td>
                    <td>${HF.escapeHtml(workRequest.updated_at || "-")}</td>
                    <td>${HF.escapeHtml(workRequest.error_message || "")}</td>
                </tr>
            `;
        }).join("");
    }

    async function loadWorkRequests(options = {}) {
        if (workRequestsPanel.hidden || (workRequestsLoading && !options.force)) {
            return;
        }

        if (workRequestsLoading) {
            return;
        }

        workRequestsLoading = true;

        try {
            const response = await fetch("/api/work-requests?category_like=ADAM.%25&limit=50", {
                cache: "no-store",
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
            });

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);

            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }

            renderWorkRequests(payload);
            await loadDataset();
        } catch (error) {
            workRequestsBody.innerHTML = `
                <tr>
                    <td colspan="5"><div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div></td>
                </tr>
            `;
        } finally {
            workRequestsLoading = false;
        }
    }

    datasetToggle.addEventListener("click", () => setActiveView("dataset"));
    workRequestsToggle.addEventListener("click", () => setActiveView("work-requests"));
    datasetCategory.addEventListener("change", () => {
        renderDataset(null);
        setStatus("");
        loadDataset();
    });
    trainingImport.addEventListener("click", () => trainingInput.click());
    testingImport.addEventListener("click", () => testingInput.click());
    trainingModel.addEventListener("click", queueTraining);

    trainingInput.addEventListener("change", () => {
        const file = trainingInput.files && trainingInput.files[0];

        if (file) {
            uploadDataset(file, "training");
        }
    });

    testingInput.addEventListener("change", () => {
        const file = testingInput.files && testingInput.files[0];

        if (file) {
            uploadDataset(file, "testing");
        }
    });

    window.setInterval(() => loadWorkRequests(), workRequestRefreshMs);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && !workRequestsPanel.hidden) {
            loadWorkRequests({force: true});
        }
    });

    setActiveView("dataset");
    renderDataset(null);
    loadDataset();
})();
