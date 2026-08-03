(function () {
    const state = document.getElementById("adam-state");
    const wakeWordToggle = document.getElementById("adam-wake-word-toggle");
    const wakeWordPanel = document.getElementById("adam-wake-word-panel");
    const wakeWordActions = document.getElementById("adam-wake-word-actions");
    const wakeWordState = document.getElementById("adam-wake-word-state");
    const wakeWordProgress = document.getElementById("adam-wake-word-progress");
    const wakeWordStart = document.getElementById("adam-wake-word-start");
    const wakeWordCancel = document.getElementById("adam-wake-word-cancel");
    const datasetToggle = document.getElementById("adam-dataset-toggle");
    const datasetPanel = document.getElementById("adam-dataset-panel");
    const textClassificationToggle = document.getElementById("adam-text-classification-toggle");
    const textClassificationPanel = document.getElementById("adam-text-classification-panel");
    const playgroundToggle = document.getElementById("adam-playground-toggle");
    const playgroundPanel = document.getElementById("adam-playground-panel");
    const playgroundMode = document.getElementById("adam-playground-mode");
    const playgroundInput = document.getElementById("adam-playground-input");
    const playgroundRun = document.getElementById("adam-playground-run");
    const playgroundIntent = document.getElementById("adam-playground-intent");
    const playgroundConfidence = document.getElementById("adam-playground-confidence");
    const playgroundMessage = document.getElementById("adam-playground-message");
    const classificationModelState = document.getElementById("adam-classification-model-state");
    const classificationEmpty = document.getElementById("adam-classification-empty");
    const classificationDetails = document.getElementById("adam-classification-details");
    const classificationModel = document.getElementById("adam-classification-model");
    const classificationAlgorithm = document.getElementById("adam-classification-algorithm");
    const classificationVectorizer = document.getElementById("adam-classification-vectorizer");
    const classificationCompleted = document.getElementById("adam-classification-completed");
    const classificationTrainingRecords = document.getElementById("adam-classification-training-records");
    const classificationTestingRecords = document.getElementById("adam-classification-testing-records");
    const classificationLabels = document.getElementById("adam-classification-labels");
    const classificationDatasets = document.getElementById("adam-classification-datasets");
    const classificationTrainingAccuracy = document.getElementById("adam-classification-training-accuracy");
    const classificationTestingAccuracy = document.getElementById("adam-classification-testing-accuracy");
    const classificationPrecision = document.getElementById("adam-classification-precision");
    const classificationRecall = document.getElementById("adam-classification-recall");
    const classificationF1 = document.getElementById("adam-classification-f1");
    const classificationChartWrap = document.getElementById("adam-classification-chart-wrap");
    const classificationChart = document.getElementById("adam-classification-chart");
    const classificationChartOpen = document.getElementById("adam-classification-chart-open");
    const classificationChartModal = document.getElementById("adam-classification-chart-modal");
    const classificationChartModalImage = document.getElementById("adam-classification-chart-modal-image");
    const classificationDatasetField = document.getElementById("adam-classification-dataset-field");
    const classificationDataset = document.getElementById("adam-classification-dataset");
    const classificationDeleteActions = document.getElementById("adam-classification-delete-actions");
    const classificationDelete = document.getElementById("adam-classification-delete");
    const trainingErrorModal = document.getElementById("adam-training-error-modal");
    const trainingErrorMessage = document.getElementById("adam-training-error-message");
    const trainingErrorClose = document.getElementById("adam-training-error-close");
    const deleteModal = document.getElementById("adam-delete-modal");
    const deleteModalCopy = document.getElementById("adam-delete-modal-copy");
    const deleteCancel = document.getElementById("adam-delete-cancel");
    const deleteConfirm = document.getElementById("adam-delete-confirm");
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
    let selectedTrainingFile = null;
    let selectedTestingFile = null;
    let trainingInProgress = false;
    let workRequestsLoading = false;
    let textClassificationLoading = false;
    let activeTraining = null;
    let deletionQueueing = false;
    let playgroundInferenceRunning = false;

    if (!wakeWordToggle || !wakeWordPanel || !wakeWordActions || !wakeWordState
            || !wakeWordProgress || !wakeWordStart || !wakeWordCancel
            || !datasetToggle || !datasetPanel || !textClassificationToggle
            || !textClassificationPanel || !playgroundToggle || !playgroundPanel
            || !playgroundMode || !playgroundInput || !playgroundRun
            || !playgroundIntent || !playgroundConfidence || !playgroundMessage
            || !workRequestsToggle || !workRequestsPanel
            || !datasetCategory || !trainingInput || !testingInput || !trainingImport || !testingImport
            || !trainingName || !testingName || !trainingModel || !classificationDeleteActions
            || !classificationDelete || !classificationDatasetField || !classificationDataset
            || !classificationChartOpen || !classificationChartModal || !classificationChartModalImage
            || !trainingErrorModal || !trainingErrorMessage || !trainingErrorClose
            || !deleteModal || !deleteModalCopy || !deleteCancel || !deleteConfirm) {
        return;
    }

    function setActiveView(view) {
        const wakeWordSelected = view === "wake-word";
        const datasetSelected = view === "dataset";
        const textClassificationSelected = view === "text-classification";
        const playgroundSelected = view === "playground";
        const workRequestsSelected = view === "work-requests";
        wakeWordPanel.hidden = !wakeWordSelected;
        wakeWordActions.hidden = !wakeWordSelected;
        datasetPanel.hidden = !datasetSelected;
        textClassificationPanel.hidden = !textClassificationSelected;
        classificationDeleteActions.hidden = !textClassificationSelected || !activeTraining;
        playgroundPanel.hidden = !playgroundSelected;
        workRequestsPanel.hidden = !workRequestsSelected;
        wakeWordToggle.classList.toggle("active", wakeWordSelected);
        datasetToggle.classList.toggle("active", datasetSelected);
        textClassificationToggle.classList.toggle("active", textClassificationSelected);
        playgroundToggle.classList.toggle("active", playgroundSelected);
        workRequestsToggle.classList.toggle("active", workRequestsSelected);
        wakeWordToggle.setAttribute("aria-expanded", wakeWordSelected ? "true" : "false");
        datasetToggle.setAttribute("aria-expanded", datasetSelected ? "true" : "false");
        textClassificationToggle.setAttribute(
            "aria-expanded",
            textClassificationSelected ? "true" : "false",
        );
        playgroundToggle.setAttribute(
            "aria-expanded",
            playgroundSelected ? "true" : "false",
        );

        if (textClassificationSelected) {
            loadTextClassification();
        } else if (datasetSelected) {
            loadActiveDatasetNames();
        } else if (workRequestsSelected) {
            loadWorkRequests({force: true});
        }
    }

    function renderWakeWordStatus(detail = {}) {
        const completedSamples = Number(detail.completedSamples) || 0;
        const requiredSamples = Number(detail.requiredSamples) || 5;
        const status = detail.state || "required";
        const enrolled = Boolean(detail.enrolled);
        const inProgress = ["starting", "recording", "progress", "invalid"].includes(status);
        const message = detail.message || "Wake word setup required";
        wakeWordState.textContent = `status=${message}`;
        wakeWordProgress.textContent = `${completedSamples}/${requiredSamples}`;
        wakeWordStart.disabled = inProgress;
        wakeWordStart.textContent = "Train Wake Word";
        wakeWordCancel.hidden = !inProgress;
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

    function setPlaygroundMessage(message, isError = false) {
        playgroundMessage.textContent = message;
        playgroundMessage.parentElement.classList.toggle("error", isError);
    }

    function syncPlaygroundControls() {
        const text = playgroundInput.value.trim();
        const textClassification = playgroundMode.value === "text-classification";
        playgroundInput.disabled = playgroundInferenceRunning;
        playgroundMode.disabled = playgroundInferenceRunning;
        playgroundRun.disabled = playgroundInferenceRunning || !textClassification || !text;

        if (!playgroundInferenceRunning && !textClassification) {
            setPlaygroundMessage("LLM inference is not available yet.");
        } else if (!playgroundInferenceRunning && !text) {
            setPlaygroundMessage("Enter text to run inference.");
        }
    }

    async function runPlaygroundInference() {
        if (playgroundInferenceRunning || playgroundMode.value !== "text-classification") {
            return;
        }

        const text = playgroundInput.value.trim();
        if (!text) {
            syncPlaygroundControls();
            return;
        }

        playgroundInferenceRunning = true;
        playgroundRun.textContent = "Running...";
        playgroundIntent.textContent = "-";
        playgroundConfidence.textContent = "-";
        setPlaygroundMessage("Running text classification inference.");
        syncPlaygroundControls();

        try {
            const response = await fetch("/api/adam/playground/text-classification", {
                method: "POST",
                credentials: "same-origin",
                headers: {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({text}),
            });

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);
            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }

            const prediction = payload.prediction || {};
            playgroundIntent.textContent = prediction.intent || "-";
            playgroundConfidence.textContent = formatScore(prediction.confidence);
            setPlaygroundMessage("Inference completed.");
        } catch (error) {
            setPlaygroundMessage(error.message, true);
        } finally {
            playgroundInferenceRunning = false;
            playgroundRun.textContent = "Run Inference";
            syncPlaygroundControls();
        }
    }

    function syncControls() {
        const busy = uploadInProgress || trainingInProgress;
        const filesSelected = Boolean(
            datasetCategory.value && selectedTrainingFile && selectedTestingFile,
        );
        trainingInput.disabled = busy;
        testingInput.disabled = busy;
        datasetCategory.disabled = busy;
        trainingImport.disabled = busy;
        testingImport.disabled = busy;
        trainingModel.disabled = busy || !filesSelected;
    }

    function renderActiveDatasetNames(training) {
        if (selectedTrainingFile || selectedTestingFile) {
            return;
        }

        const datasets = training?.datasets || [];
        const trainingDataset = datasets.find((dataset) => dataset.purpose === "training");
        const testingDataset = datasets.find((dataset) => dataset.purpose === "testing");

        trainingName.value = trainingDataset?.file_name || "";
        testingName.value = testingDataset?.file_name || "";
    }

    async function loadActiveDatasetNames() {
        if (selectedTrainingFile || selectedTestingFile) {
            return;
        }

        try {
            const response = await fetch("/api/adam/text-classification", {
                cache: "no-store",
                credentials: "same-origin",
                headers: {"Accept": "application/json"},
            });

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);

            if (!response.ok) {
                throw new Error(payload.detail || ("HTTP " + response.status));
            }

            renderActiveDatasetNames(payload.training || null);
        } catch (error) {
            // Keep the dataset selection controls usable if model data is unavailable.
        }
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

    function selectDataset(file, type) {
        if (!validateFile(file)) return;
        if (type === "training") { selectedTrainingFile = file; trainingName.value = file.name; }
        else { selectedTestingFile = file; testingName.value = file.name; }
        setState(selectedTrainingFile && selectedTestingFile ? "Ready to train selected datasets" : "Select the remaining dataset");
        setStatus(`${type === "training" ? "Training" : "Testing"} dataset selected. It will upload when Train Model is clicked.`);
        syncControls();
    }

    function clearSelectedDatasets() {
        selectedTrainingFile = null;
        selectedTestingFile = null;
        trainingInput.value = "";
        testingInput.value = "";
        trainingName.value = "";
        testingName.value = "";
    }

    async function queueTraining() {
        if (!selectedTrainingFile || !selectedTestingFile) { setStatus("Select both training and testing CSV files first.", true); return; }
        trainingInProgress = true; syncControls(); trainingModel.textContent = "Uploading and queueing..."; setState("Validating selected datasets"); setStatus("");
        try {
            const formData = new FormData();
            formData.append("dataset_category", datasetCategory.value);
            formData.append("training_dataset", selectedTrainingFile, selectedTrainingFile.name);
            formData.append("testing_dataset", selectedTestingFile, selectedTestingFile.name);
            const response = await fetch("/api/adam/text-classification/training", {method: "POST", credentials: "same-origin", headers: {"Accept": "application/json"}, body: formData});
            if (handleAuthentication(response)) return;
            const payload = await parseResponse(response);
            if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
            selectedTrainingFile = null; selectedTestingFile = null; trainingInput.value = ""; testingInput.value = "";
            renderDataset(payload.dataset); setStatus(payload.message || "Training work request queued successfully."); setActiveView("work-requests");
        } catch (error) {
            const message = error.message || "The training request could not be completed.";
            clearSelectedDatasets();
            setState("Error");
            setStatus(message, true);
            showTrainingError(message);
        }
        finally { trainingInProgress = false; trainingModel.textContent = "Train Model"; syncControls(); }
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

    function formatScore(value) {
        const numericValue = Number(value);

        if (!Number.isFinite(numericValue)) {
            return "-";
        }

        return `${(numericValue * 100).toFixed(2)}%`;
    }

    function renderTextClassification(training) {
        const available = Boolean(training);
        activeTraining = training || null;
        classificationEmpty.hidden = available;
        classificationDetails.hidden = !available;
        classificationDeleteActions.hidden = !available || textClassificationPanel.hidden;
        classificationDelete.disabled = !available || deletionQueueing;
        classificationDataset.disabled = !available;
        classificationDatasetField.hidden = !available;
        classificationModelState.textContent = available
            ? "model=active"
            : "model=unavailable";

        if (!available) {
            classificationDataset.innerHTML = "";
            classificationDataset.value = "";
            classificationEmpty.querySelector("span:last-child").textContent =
                "No trained model available.";
            classificationChartWrap.hidden = true;
            classificationChart.removeAttribute("src");
            closeClassificationChart();
            setState("Waiting for trained model");
            return;
        }

        const metrics = training.metrics || {};
        const datasets = training.datasets || [];
        const categoryOptions = training.dataset_categories || [];
        const selectedCategory = training.selected_category || categoryOptions[0]?.value || "";
        classificationDataset.innerHTML = categoryOptions.map((category) => (
            `<option value="${HF.escapeHtml(category.value)}">${HF.escapeHtml(category.label)}</option>`
        )).join("");
        classificationDataset.value = selectedCategory;
        classificationModel.textContent = training.model_file || "-";
        classificationAlgorithm.textContent = training.algorithm || "-";
        classificationVectorizer.textContent = training.vectorizer || "-";
        classificationCompleted.textContent = training.completed_at
            ? new Date(`${training.completed_at}Z`).toLocaleString("en-US")
            : "-";
        classificationTrainingRecords.textContent = String(training.training_records || 0);
        classificationTestingRecords.textContent = String(training.testing_records || 0);
        classificationLabels.textContent = (training.labels || []).join(", ") || "-";
        const visibleDatasets = selectedCategory
            ? datasets.filter((dataset) => dataset.category === selectedCategory)
            : datasets;
        classificationDatasets.textContent = visibleDatasets.map((dataset) => (
            `${dataset.category_name || dataset.category}/${dataset.purpose}: ${dataset.file_name} (${dataset.records})`
        )).join(" | ") || "-";
        classificationTrainingAccuracy.textContent = formatScore(metrics.training_accuracy);
        classificationTestingAccuracy.textContent = formatScore(metrics.testing_accuracy);
        classificationPrecision.textContent = formatScore(metrics.precision_macro);
        classificationRecall.textContent = formatScore(metrics.recall_macro);
        classificationF1.textContent = formatScore(metrics.f1_macro);
        classificationChartWrap.hidden = !training.chart_url;

        if (training.chart_url) {
            classificationChart.src = training.chart_url;
        } else {
            classificationChart.removeAttribute("src");
        }

        setState("Model available");

        if (!training.selected_category && selectedCategory) {
            window.setTimeout(loadTextClassification, 0);
        }
    }

    function openClassificationChart() {
        const chartUrl = classificationChart.getAttribute("src");

        if (!chartUrl) {
            return;
        }

        classificationChartModalImage.src = chartUrl;
        classificationChartModal.hidden = false;
        document.body.classList.add("graph-modal-open");
    }

    function closeClassificationChart() {
        classificationChartModal.hidden = true;
        classificationChartModalImage.removeAttribute("src");
        document.body.classList.remove("graph-modal-open");
    }

    function showTrainingError(message) {
        trainingErrorMessage.textContent = message;
        trainingErrorModal.hidden = false;
        trainingErrorClose.focus();
    }

    function closeTrainingError() {
        trainingErrorModal.hidden = true;
        trainingModel.focus();
    }

    function openDeleteModal() {
        if (!activeTraining || deletionQueueing) {
            return;
        }

        deleteModalCopy.textContent =
            "Delete the active model, evaluation chart, and all datasets used to train it? "
            + "This action cannot be undone.";
        deleteConfirm.textContent = "Delete";
        deleteConfirm.disabled = false;
        deleteCancel.disabled = false;
        deleteModal.hidden = false;
        deleteCancel.focus();
    }

    function closeDeleteModal() {
        if (deletionQueueing) {
            return;
        }

        deleteModal.hidden = true;
        classificationDelete.focus();
    }

    async function queueDeletion() {
        if (!activeTraining || deletionQueueing) {
            return;
        }

        deletionQueueing = true;
        classificationDelete.disabled = true;
        deleteCancel.disabled = true;
        deleteConfirm.disabled = true;
        deleteConfirm.textContent = "Queueing...";
        setState("Queueing deletion");
        let queued = false;

        try {
            const trainingUid = encodeURIComponent(activeTraining.training_uid);
            const response = await fetch(
                `/api/adam/text-classification?training_uid=${trainingUid}`,
                {
                    method: "DELETE",
                    credentials: "same-origin",
                    headers: {"Accept": "application/json"},
                },
            );

            if (handleAuthentication(response)) {
                return;
            }

            const payload = await parseResponse(response);

            if (!response.ok) {
                throw new Error(payload.detail || `HTTP ${response.status}`);
            }

            queued = true;
            deleteModal.hidden = true;
            setActiveView("work-requests");
        } catch (error) {
            deleteModalCopy.textContent = error.message;
            setState("Error");
        } finally {
            deletionQueueing = false;
            deleteCancel.disabled = false;
            deleteConfirm.disabled = false;
            deleteConfirm.textContent = "Delete";
            classificationDelete.disabled = !activeTraining;

            if (queued) {
                deleteModal.hidden = true;
            }
        }
    }

    async function loadTextClassification() {
        if (textClassificationPanel.hidden || textClassificationLoading) {
            return;
        }

        textClassificationLoading = true;
        classificationModelState.textContent = "model=loading";

        try {
            const category = classificationDataset.value;
            const query = category
                ? `?dataset_category=${encodeURIComponent(category)}`
                : "";
            const response = await fetch(`/api/adam/text-classification${query}`, {
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

            const training = payload.training || null;
            renderTextClassification(training);
            renderActiveDatasetNames(training);
        } catch (error) {
            classificationDetails.hidden = true;
            classificationEmpty.hidden = false;
            classificationEmpty.querySelector("span:last-child").textContent = error.message;
            classificationModelState.textContent = "model=error";
            setState("Error");
        } finally {
            textClassificationLoading = false;
        }
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

    wakeWordToggle.addEventListener("click", () => setActiveView("wake-word"));
    wakeWordStart.addEventListener("click", () => {
        document.dispatchEvent(new CustomEvent("adam:wake-word:enroll"));
    });
    wakeWordCancel.addEventListener("click", () => {
        document.dispatchEvent(new CustomEvent("adam:wake-word:cancel"));
    });
    document.addEventListener("adam:wake-word-status", (event) => {
        renderWakeWordStatus(event.detail);
    });
    datasetToggle.addEventListener("click", () => setActiveView("dataset"));
    textClassificationToggle.addEventListener(
        "click",
        () => setActiveView("text-classification"),
    );
    playgroundToggle.addEventListener("click", () => setActiveView("playground"));
    workRequestsToggle.addEventListener("click", () => setActiveView("work-requests"));
    datasetCategory.addEventListener("change", () => {
        selectedTrainingFile = null; selectedTestingFile = null; trainingInput.value = ""; testingInput.value = "";
        renderDataset(null);
        setStatus("");
    });
    trainingImport.addEventListener("click", () => trainingInput.click());
    testingImport.addEventListener("click", () => testingInput.click());
    trainingModel.addEventListener("click", queueTraining);
    playgroundInput.addEventListener("input", syncPlaygroundControls);
    playgroundMode.addEventListener("change", syncPlaygroundControls);
    playgroundRun.addEventListener("click", runPlaygroundInference);
    classificationDataset.addEventListener("change", loadTextClassification);
    classificationChartOpen.addEventListener("click", openClassificationChart);
    classificationChartModal.addEventListener("click", (event) => {
        if (event.target.closest("[data-adam-chart-modal-close]")) {
            closeClassificationChart();
        }
    });
    classificationDelete.addEventListener("click", openDeleteModal);
    trainingErrorClose.addEventListener("click", closeTrainingError);
    trainingErrorModal.addEventListener("click", (event) => {
        if (event.target === trainingErrorModal) {
            closeTrainingError();
        }
    });
    deleteCancel.addEventListener("click", closeDeleteModal);
    deleteConfirm.addEventListener("click", queueDeletion);
    deleteModal.addEventListener("click", (event) => {
        if (event.target === deleteModal) {
            closeDeleteModal();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") {
            return;
        }
        if (!classificationChartModal.hidden) {
            closeClassificationChart();
        } else if (!trainingErrorModal.hidden) {
            closeTrainingError();
        } else if (!deleteModal.hidden) {
            closeDeleteModal();
        }
    });

    trainingInput.addEventListener("change", () => {
        const file = trainingInput.files && trainingInput.files[0];

        if (file) {
            selectDataset(file, "training");
        }
    });

    testingInput.addEventListener("change", () => {
        const file = testingInput.files && testingInput.files[0];

        if (file) {
            selectDataset(file, "testing");
        }
    });

    window.setInterval(() => loadWorkRequests(), workRequestRefreshMs);
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && !workRequestsPanel.hidden) {
            loadWorkRequests({force: true});
        }
    });

    renderWakeWordStatus();
    setActiveView("wake-word");
    document.dispatchEvent(new CustomEvent("adam:wake-word:status:request"));
    renderDataset(null);
    loadActiveDatasetNames();
    syncPlaygroundControls();
})();
