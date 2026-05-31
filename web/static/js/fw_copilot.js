(function () {
    const copilot = document.querySelector("[data-fw-copilot]");
    if (!copilot) {
        return;
    }

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    let trackingTimer = null;

    function setTracking(active) {
        copilot.dataset.tracking = active ? "true" : "false";
    }

    function trackPointer(event) {
        const rect = copilot.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const dx = clamp((event.clientX - centerX) / window.innerWidth, -0.5, 0.5);
        const dy = clamp((event.clientY - centerY) / window.innerHeight, -0.5, 0.5);

        copilot.style.setProperty("--copilot-eye-x", `${dx * 4}px`);
        copilot.style.setProperty("--copilot-eye-y", `${dy * 3}px`);
        copilot.style.setProperty("--copilot-glow", String(0.45 + Math.abs(dx) * 0.45));

        setTracking(true);
        window.clearTimeout(trackingTimer);
        trackingTimer = window.setTimeout(() => setTracking(false), 900);
    }

    window.addEventListener("pointermove", trackPointer, { passive: true });
    copilot.addEventListener("click", () => {
        copilot.classList.add("is-pulsing");
        window.setTimeout(() => copilot.classList.remove("is-pulsing"), 520);
    });
})();
