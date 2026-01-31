const form = document.getElementById("settings-form");
const ssoUrlInput = document.getElementById("sso-url");
const ssoRegionInput = document.getElementById("sso-region");
const accountIdInput = document.getElementById("account-id");
const roleNameInput = document.getElementById("role-name");
const awsRegionInput = document.getElementById("aws-region");
const dbNameInput = document.getElementById("db-name");
const dbUserInput = document.getElementById("db-user");
const tagKeyInput = document.getElementById("tag-key");
const tagValueInput = document.getElementById("tag-value");
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

function setStatus(message, isError = false, allowHtml = false) {
  if (allowHtml) {
    statusEl.innerHTML = message;
  } else {
    statusEl.textContent = message;
  }
  statusEl.classList.toggle("error", isError);
}

function setDeviceStatus(message, isError = false, allowHtml = false) {
  if (allowHtml) {
    deviceStatus.innerHTML = message;
  } else {
    deviceStatus.textContent = message;
  }
  deviceStatus.classList.toggle("error", isError);
}

function formatMissingSettingMessage(payload) {
  if (!payload || payload.error_code !== "missing_required_setting") return null;
  return `Missing required setting ${payload.setting}. Update it on the <a href="/settings.html">settings page</a>.`;
}

async function refreshSsoStatus() {
  try {
    const response = await fetch("/api/sso/status");
    const payload = await response.json();
    if (!response.ok) {
      const missingMessage = formatMissingSettingMessage(payload);
      if (missingMessage) {
        setDeviceStatus(missingMessage, true, true);
        return;
      }
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
    ssoRegionInput.value = payload.settings?.sso_region || "";
    accountIdInput.value = payload.settings?.account_id || "";
    roleNameInput.value = payload.settings?.role_name || "";
    awsRegionInput.value = payload.settings?.aws_region || "";
    dbNameInput.value = payload.settings?.db_name || "";
    dbUserInput.value = payload.settings?.db_user || "";
    tagKeyInput.value = payload.settings?.tag_key || "";
    tagValueInput.value = payload.settings?.tag_value || "";
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
      body: JSON.stringify({
        sso_url: ssoUrlInput.value.trim(),
        sso_region: ssoRegionInput.value.trim(),
        account_id: accountIdInput.value.trim(),
        role_name: roleNameInput.value.trim(),
        aws_region: awsRegionInput.value.trim(),
        db_name: dbNameInput.value.trim(),
        db_user: dbUserInput.value.trim(),
        tag_key: tagKeyInput.value.trim(),
        tag_value: tagValueInput.value.trim(),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const missingMessage = formatMissingSettingMessage(payload);
      if (missingMessage) {
        setStatus(missingMessage, true, true);
        return;
      }
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
      const missingMessage = formatMissingSettingMessage(payload);
      if (missingMessage) {
        setDeviceStatus(missingMessage, true, true);
        return;
      }
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
          const missingMessage = formatMissingSettingMessage(pollPayload);
          if (missingMessage) {
            setDeviceStatus(missingMessage, true, true);
            clearInterval(devicePollTimer);
            devicePollTimer = null;
            return;
          }
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
