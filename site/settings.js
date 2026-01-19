const form = document.getElementById("settings-form");
const ssoUrlInput = document.getElementById("sso-url");
const statusEl = document.getElementById("settings-status");
const loginButton = document.getElementById("sso-login");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

async function loadSettings() {
  try {
    const response = await fetch("/api/global-settings");
    if (!response.ok) throw new Error("Unable to load settings.");
    const payload = await response.json();
    ssoUrlInput.value = payload.settings?.sso_url || "";
  } catch (error) {
    setStatus("Unable to load settings.", true);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await fetch("/api/global-settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sso_url: ssoUrlInput.value.trim() }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to save settings.");
    }
    setStatus("Settings saved.");
  } catch (error) {
    setStatus(error.message || "Unable to save settings.", true);
  }
});

loginButton.addEventListener("click", () => {
  window.location.assign("/login");
});

loadSettings();
