(function () {
    const state = document.getElementById("users-state");
    const body = document.getElementById("users-body");
    const addButton = document.getElementById("user-add-button");
    const userModal = document.getElementById("user-modal");
    const userForm = document.getElementById("user-form");
    const userFormStatus = document.getElementById("user-form-status");
    const passwordModal = document.getElementById("password-modal");
    const passwordForm = document.getElementById("password-form");
    const passwordFormStatus = document.getElementById("password-form-status");
    const confirmModal = document.getElementById("confirm-modal");
    const confirmMessage = document.getElementById("confirm-message");
    const confirmAccept = document.getElementById("confirm-accept");
    let users = [];
    let confirmAction = null;

    function setState(value) {
        if (state) {
            state.textContent = value;
        }
    }

    function setStatus(element, message, isError = false) {
        if (!element) {
            return;
        }
        element.textContent = message || "";
        element.classList.toggle("error", Boolean(isError));
    }

    async function requestJson(url, options = {}) {
        const response = await fetch(url, {
            cache: "no-store",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                ...(options.headers || {}),
            },
            ...options,
        });

        if (response.status === 401) {
            window.location.href = "/login";
            return null;
        }
        if (response.status === 403) {
            window.location.href = "/login/change-password";
            return null;
        }

        const text = await response.text();
        let payload = {};
        if (text) {
            try {
                payload = JSON.parse(text);
            } catch (error) {
                payload = { detail: text.trim() || "Invalid server response." };
            }
        }
        if (!response.ok) {
            throw new Error(payload.detail || `HTTP ${response.status}`);
        }
        return payload;
    }

    function statusBadge(user) {
        return Number(user.enabled) === 1
            ? '<span class="status up">ENABLED</span>'
            : '<span class="status disabled">DISABLED</span>';
    }

    function flagsFor(user) {
        const flags = [];
        if (Number(user.protected) === 1) {
            flags.push('<span class="status protected">PROTECTED</span>');
        }
        if (Number(user.must_change_password) === 1) {
            flags.push('<span class="status pending">PASSWORD CHANGE</span>');
        }
        return flags.length ? flags.join(" ") : '<span class="muted">-</span>';
    }

    function renderUsers() {
        if (!body) {
            return;
        }

        if (!users.length) {
            body.innerHTML = `
                <tr>
                    <td colspan="8">
                        <div class="terminal-empty"><span class="prompt">$</span><span>no users</span></div>
                    </td>
                </tr>
            `;
            return;
        }

        body.innerHTML = users.map((user) => {
            const disabledProtected = Number(user.protected) === 1;
            const enabled = Number(user.enabled) === 1;
            return `
                <tr class="${enabled ? "" : "is-disabled"} ${disabledProtected ? "is-protected" : ""}">
                    <td><strong>${HF.escapeHtml(user.username)}</strong></td>
                    <td>${HF.escapeHtml(user.display_name || "-")}</td>
                    <td><span class="role">${HF.escapeHtml(user.role)}</span></td>
                    <td>${statusBadge(user)}</td>
                    <td>${flagsFor(user)}</td>
                    <td>${HF.escapeHtml(user.last_login_at || "-")}</td>
                    <td>${HF.escapeHtml(user.failed_login_count)}</td>
                    <td>
                        <div class="table-actions">
                            <button class="icon-button" type="button" data-user-edit="${user.id}" aria-label="Edit ${HF.escapeHtml(user.username)}">E</button>
                            <button class="icon-button" type="button" data-user-password="${user.id}" aria-label="Reset ${HF.escapeHtml(user.username)} password">K</button>
                            <button class="text-button compact" type="button" data-user-enabled="${user.id}" data-enabled="${enabled ? "0" : "1"}" ${disabledProtected && enabled ? "disabled" : ""}>${enabled ? "Disable" : "Enable"}</button>
                            <button class="text-button compact danger" type="button" data-user-delete="${user.id}" ${disabledProtected ? "disabled" : ""}>Delete</button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    async function loadUsers() {
        try {
            setState("Polling");
            const data = await requestJson("/api/settings/users");
            if (!data) {
                return;
            }
            users = data.users || [];
            renderUsers();
            setState("Live");
        } catch (error) {
            setState("Error");
            if (body) {
                body.innerHTML = `
                    <tr>
                        <td colspan="8">
                            <div class="terminal-empty"><span class="prompt">$</span><span>${HF.escapeHtml(error.message)}</span></div>
                        </td>
                    </tr>
                `;
            }
        }
    }

    function findUser(userId) {
        return users.find((user) => Number(user.id) === Number(userId));
    }

    function openUserModal(user = null) {
        userForm.reset();
        setStatus(userFormStatus, "");
        userForm.elements.id.value = user ? user.id : "";
        userForm.elements.username.value = user ? user.username : "";
        userForm.elements.username.readOnly = Boolean(user);
        userForm.elements.display_name.value = user ? user.display_name || "" : "";
        userForm.elements.role.value = user ? user.role : "viewer";
        userForm.elements.password.value = "";
        userForm.elements.password.required = !user;
        userForm.querySelector("[data-password-field]").hidden = Boolean(user);
        userForm.elements.must_change_password.checked = user ? Number(user.must_change_password) === 1 : true;
        document.getElementById("user-modal-title").textContent = user ? "Edit user" : "Add user";
        userModal.hidden = false;
    }

    function closeUserModal() {
        userModal.hidden = true;
    }

    function openPasswordModal(user) {
        passwordForm.reset();
        setStatus(passwordFormStatus, "");
        passwordForm.elements.id.value = user.id;
        passwordForm.elements.must_change_password.checked = true;
        document.getElementById("password-modal-title").textContent = `Reset password / ${user.username}`;
        passwordModal.hidden = false;
        passwordForm.elements.password.focus();
    }

    function closePasswordModal() {
        passwordModal.hidden = true;
    }

    function openConfirm(message, action) {
        confirmMessage.textContent = message;
        confirmAction = action;
        confirmModal.hidden = false;
    }

    function closeConfirm() {
        confirmModal.hidden = true;
        confirmAction = null;
    }

    async function saveUser(event) {
        event.preventDefault();
        const id = userForm.elements.id.value;
        const payload = {
            username: userForm.elements.username.value,
            display_name: userForm.elements.display_name.value,
            role: userForm.elements.role.value,
            must_change_password: userForm.elements.must_change_password.checked,
        };
        if (!id) {
            payload.password = userForm.elements.password.value;
        }

        try {
            await requestJson(id ? `/api/settings/users/${id}` : "/api/settings/users", {
                method: id ? "PUT" : "POST",
                body: JSON.stringify(payload),
            });
            closeUserModal();
            await loadUsers();
        } catch (error) {
            setStatus(userFormStatus, error.message, true);
        }
    }

    async function savePassword(event) {
        event.preventDefault();
        const id = passwordForm.elements.id.value;
        try {
            await requestJson(`/api/settings/users/${id}/password`, {
                method: "PUT",
                body: JSON.stringify({
                    password: passwordForm.elements.password.value,
                    must_change_password: passwordForm.elements.must_change_password.checked,
                }),
            });
            closePasswordModal();
            await loadUsers();
        } catch (error) {
            setStatus(passwordFormStatus, error.message, true);
        }
    }

    document.addEventListener("click", (event) => {
        const editButton = event.target.closest("[data-user-edit]");
        const passwordButton = event.target.closest("[data-user-password]");
        const enabledButton = event.target.closest("[data-user-enabled]");
        const deleteButton = event.target.closest("[data-user-delete]");

        if (event.target.closest("[data-user-modal-close]")) {
            closeUserModal();
            return;
        }
        if (event.target.closest("[data-password-modal-close]")) {
            closePasswordModal();
            return;
        }
        if (event.target.closest("[data-confirm-cancel]")) {
            closeConfirm();
            return;
        }
        if (editButton) {
            const user = findUser(editButton.dataset.userEdit);
            if (user) openUserModal(user);
            return;
        }
        if (passwordButton) {
            const user = findUser(passwordButton.dataset.userPassword);
            if (user) openPasswordModal(user);
            return;
        }
        if (enabledButton) {
            const user = findUser(enabledButton.dataset.userEnabled);
            const enabled = enabledButton.dataset.enabled === "1";
            if (user) {
                openConfirm(`${enabled ? "Enable" : "Disable"} user ${user.username}?`, async () => {
                    await requestJson(`/api/settings/users/${user.id}/enabled`, {
                        method: "PUT",
                        body: JSON.stringify({ enabled }),
                    });
                    await loadUsers();
                });
            }
            return;
        }
        if (deleteButton) {
            const user = findUser(deleteButton.dataset.userDelete);
            if (user) {
                openConfirm(`Delete user ${user.username}?`, async () => {
                    await requestJson(`/api/settings/users/${user.id}`, { method: "DELETE" });
                    await loadUsers();
                });
            }
        }
    });

    if (addButton) {
        addButton.addEventListener("click", () => openUserModal());
    }
    if (userForm) {
        userForm.addEventListener("submit", saveUser);
    }
    if (passwordForm) {
        passwordForm.addEventListener("submit", savePassword);
    }
    if (confirmAccept) {
        confirmAccept.addEventListener("click", async () => {
            if (!confirmAction) {
                closeConfirm();
                return;
            }
            try {
                const action = confirmAction;
                closeConfirm();
                await action();
            } catch (error) {
                setState(`Error ${error.message}`);
            }
        });
    }

    loadUsers();
}());
