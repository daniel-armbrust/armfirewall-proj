(() => {
    const integrationOpenButton = document.getElementById("oci-integration-open");
    const integrationPanel = document.getElementById("oci-integration-panel");
    const savedIntegration = document.getElementById("oci-integration-saved");
    const savedAuthenticationType = document.getElementById("oci-integration-authentication-type");
    const form = document.getElementById("oci-integration-form");
    const authenticationType = document.getElementById("oci-authentication-type");
    const keyFields = [...document.querySelectorAll("[data-oci-key-field]")];
    const privateKey = document.getElementById("oci-private-key");
    const region = document.getElementById("oci-region");
    const fingerprint = document.getElementById("oci-fingerprint");
    const status = document.getElementById("oci-integration-status");
    const applyButton = document.getElementById("oci-integration-apply");
    const editButton = document.getElementById("oci-integration-edit");
    const deleteButton = document.getElementById("oci-integration-delete");
    const testButton = document.getElementById("oci-integration-test");
    const testModal = document.getElementById("oci-integration-test-modal");
    const testModalTitle = document.getElementById("oci-integration-test-title");
    const testModalMessage = document.getElementById("oci-integration-test-message");
    const testModalPrompt = document.getElementById("oci-integration-test-prompt");
    const testModalCloseButton = document.getElementById("oci-integration-test-modal-close");
    const testModalConfirmButton = document.getElementById("oci-integration-test-modal-confirm");
    const deleteModal = document.getElementById("oci-integration-delete-modal");
    const deleteModalCloseButton = document.getElementById("oci-integration-delete-modal-close");
    const deleteModalCancelButton = document.getElementById("oci-integration-delete-modal-cancel");
    const deleteModalConfirmButton = document.getElementById("oci-integration-delete-modal-confirm");
    const userOcid = document.querySelector("[name='user_ocid']");
    const tenancyOcid = document.querySelector("[name='tenancy_ocid']");

    if (!integrationOpenButton || !integrationPanel || !savedIntegration || !form || !authenticationType || !region || !fingerprint || !testModal || !testModalTitle || !testModalMessage || !testModalPrompt || !testModalCloseButton || !testModalConfirmButton || !deleteModal || !deleteModalCloseButton || !deleteModalCancelButton || !deleteModalConfirmButton) {
        return;
    }

    let savedConfiguration = null;

    const authenticationLabel = (value) => value === "api_key" ? "OCI API Key" : "Instance Principal";

    const setKeyFieldsEnabled = () => {
        const usesApiKey = authenticationType.value === "api_key";
        keyFields.forEach((field) => {
            field.classList.toggle("is-disabled", !usesApiKey);
            field.querySelectorAll("input, textarea, button").forEach((control) => {
                control.disabled = !usesApiKey;
            });
        });
    };

    const validateConfiguration = () => {
        if (authenticationType.value === "instance_principal") {
            return true;
        }
        return Boolean(
            userOcid.value.trim()
            && tenancyOcid.value.trim()
            && region.value
            && fingerprint.value.trim()
            && privateKey.value.trim()
        );
    };

    const setStatus = (message, isError = false) => {
        status.classList.toggle("error", isError);
        status.textContent = message;
    };

    const closeTestModal = () => {
        testModal.hidden = true;
    };

    const closeDeleteModal = () => {
        deleteModal.hidden = true;
    };

    const showTestModal = (succeeded, message) => {
        testModalTitle.textContent = succeeded ? "OCI Integration Test Succeeded" : "OCI Integration Test Failed";
        testModalMessage.textContent = message;
        testModalPrompt.textContent = succeeded ? "$" : "!";
        testModal.hidden = false;
        testModalConfirmButton.focus();
    };

    const showSavedConfiguration = (configuration) => {
        savedConfiguration = configuration;
        savedAuthenticationType.textContent = authenticationLabel(configuration.authentication_type);
        savedIntegration.hidden = false;
        form.hidden = true;
    };

    const showForm = (configuration = null) => {
        savedIntegration.hidden = true;
        form.hidden = false;
        if (configuration) {
            authenticationType.value = configuration.authentication_type;
            userOcid.value = configuration.user_ocid || "";
            tenancyOcid.value = configuration.tenancy_ocid || "";
            region.value = configuration.region || "";
            fingerprint.value = configuration.fingerprint || "";
            privateKey.value = "";
        }
        setKeyFieldsEnabled();
    };

    const request = async (url, options = {}) => {
        const response = await fetch(url, options);
        const result = await response.json();
        if (!response.ok) {
            throw new Error(result.detail || "OCI integration request failed.");
        }
        return result;
    };

    const loadSavedConfiguration = async () => {
        try {
            const configuration = await request("/api/settings/runtime/oci");
            if (configuration.configured) {
                showSavedConfiguration(configuration);
                setStatus("Saved OCI integration configuration.");
            } else {
                showForm();
                setStatus("Configuration is not saved yet.");
            }
        } catch (error) {
            showForm();
            setStatus(error instanceof Error ? error.message : "Could not load OCI integration settings.", true);
        }
    };

    const loadRegions = async () => {
        try {
            const result = await request("/api/settings/runtime/oci/regions");
            result.regions.forEach((regionName) => {
                const option = document.createElement("option");
                option.value = regionName;
                option.textContent = regionName;
                region.append(option);
            });
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Could not load OCI regions.", true);
        }
    };

    integrationOpenButton.addEventListener("click", () => {
        integrationPanel.hidden = false;
        integrationOpenButton.setAttribute("aria-expanded", "true");
        integrationOpenButton.classList.add("active");
    });

    authenticationType.addEventListener("change", () => {
        setKeyFieldsEnabled();
        setStatus(authenticationType.value === "api_key"
            ? "OCI API key fields are enabled."
            : "Instance Principal does not require OCI key material.");
    });

    applyButton.addEventListener("click", async () => {
        if (!validateConfiguration()) {
            setStatus("User OCID, Tenancy OCID, region, fingerprint and private key are required.", true);
            return;
        }
        applyButton.disabled = true;
        setStatus("Saving OCI integration settings…");
        try {
            const configuration = await request("/api/settings/runtime/oci", {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    authentication_type: authenticationType.value,
                    user_ocid: userOcid.value,
                    tenancy_ocid: tenancyOcid.value,
                    region: region.value,
                    fingerprint: fingerprint.value,
                    private_key: privateKey.value,
                }),
            });
            showSavedConfiguration(configuration);
            setStatus("OCI integration configuration saved.");
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Could not save OCI integration settings.", true);
        } finally {
            applyButton.disabled = false;
        }
    });

    editButton.addEventListener("click", () => {
        showForm(savedConfiguration);
        setStatus(savedConfiguration?.authentication_type === "api_key"
            ? "Enter the private key again before applying changes."
            : "Edit OCI integration settings.");
        authenticationType.focus();
    });

    const deleteSavedConfiguration = async () => {
        deleteButton.disabled = true;
        deleteModalConfirmButton.disabled = true;
        setStatus("Deleting OCI integration configuration…");
        try {
            await request("/api/settings/runtime/oci", {method: "DELETE"});
            savedConfiguration = null;
            form.reset();
            showForm();
            setStatus("OCI integration configuration deleted.");
            closeDeleteModal();
        } catch (error) {
            setStatus(error instanceof Error ? error.message : "Could not delete OCI integration settings.", true);
        } finally {
            deleteButton.disabled = false;
            deleteModalConfirmButton.disabled = false;
        }
    };

    deleteButton.addEventListener("click", () => {
        deleteModal.hidden = false;
        deleteModalConfirmButton.focus();
    });

    deleteModalCloseButton.addEventListener("click", closeDeleteModal);
    deleteModalCancelButton.addEventListener("click", closeDeleteModal);
    deleteModalConfirmButton.addEventListener("click", deleteSavedConfiguration);
    deleteModal.addEventListener("click", (event) => {
        if (event.target === deleteModal) {
            closeDeleteModal();
        }
    });

    testButton.addEventListener("click", async () => {
        testButton.disabled = true;
        setStatus("Testing OCI integration configuration…");
        try {
            const result = await request("/api/settings/runtime/oci/test", {method: "POST"});
            setStatus(result.message);
            showTestModal(true, result.message);
        } catch (error) {
            const message = error instanceof Error ? error.message : "OCI integration test failed.";
            setStatus(message, true);
            showTestModal(false, message);
        } finally {
            testButton.disabled = false;
        }
    });

    testModalCloseButton.addEventListener("click", closeTestModal);
    testModalConfirmButton.addEventListener("click", closeTestModal);
    testModal.addEventListener("click", (event) => {
        if (event.target === testModal) {
            closeTestModal();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            if (!testModal.hidden) {
                closeTestModal();
            }
            if (!deleteModal.hidden) {
                closeDeleteModal();
            }
        }
    });

    setKeyFieldsEnabled();
    Promise.all([loadRegions(), loadSavedConfiguration()]);
})();
