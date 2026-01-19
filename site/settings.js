const form = document.getElementById("settings-form");
const ssoUrlInput = document.getElementById("sso-url");
const statusEl = document.getElementById("settings-status");
const loginButton = document.getElementById("sso-login");
const deviceStartButton = document.getElementById("sso-device-start");
const deviceInfo = document.getElementById("sso-device-info");
const deviceLink = document.getElementById("sso-device-link");
const deviceCode = document.getElementById("sso-device-code");
const deviceStatus = document.getElementById("sso-device-status");

let devicePollTimer = null;
let deviceCodeValue = null;
let devicePollInterval = 5000;

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.classList.toggle("error", isError);
}

function setDeviceStatus(message, isError = false) {
  deviceStatus.textContent = message;
  deviceStatus.classList.toggle("error", isError);
}

async function refreshSsoStatus() {
  try {
    const response = await fetch("/api/sso/status");
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to check SSO status.");
    }
    if (payload.authenticated) {
      setDeviceStatus("SSO session is active.");
    } else {
      setDeviceStatus("SSO session is not active.", true);
    }
  } catch (error) {
    setDeviceStatus(error.message || "Unable to check SSO status.", true);
  }
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

deviceStartButton.addEventListener("click", async () => {
  if (devicePollTimer) {
    clearInterval(devicePollTimer);
    devicePollTimer = null;
  }
  try {
    const response = await fetch("/api/sso/device/start", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to start device login.");
    }
    deviceCodeValue = payload.device_code;
    devicePollInterval = Math.max(5, payload.interval || 5) * 1000;
    const link = payload.verification_uri_complete || payload.verification_uri;
    deviceLink.href = link;
    deviceLink.textContent = link;
    deviceCode.textContent = payload.user_code;
    deviceInfo.hidden = false;
    setDeviceStatus("Waiting for authorization...");

    devicePollTimer = setInterval(async () => {
      try {
        const pollResponse = await fetch("/api/sso/device/poll", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ device_code: deviceCodeValue }),
        });
        const pollPayload = await pollResponse.json();
        if (pollResponse.status === 202) {
          setDeviceStatus("Waiting for authorization...");
          return;
        }
        if (!pollResponse.ok) {
          throw new Error(pollPayload.error || "Device authorization failed.");
        }
        if (pollPayload.status === "authorized") {
          setDeviceStatus("SSO device login complete.");
          clearInterval(devicePollTimer);
          devicePollTimer = null;
          refreshSsoStatus();
        }
      } catch (error) {
        setDeviceStatus(error.message || "Device authorization failed.", true);
        clearInterval(devicePollTimer);
        devicePollTimer = null;
      }
    }, devicePollInterval);
  } catch (error) {
    setDeviceStatus(error.message || "Unable to start device login.", true);
  }
});

loadSettings();
refreshSsoStatus();
