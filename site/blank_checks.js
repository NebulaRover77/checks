const form = document.getElementById("blank-form");
const accountSelect = document.getElementById("account-select");
const accountLoadButton = document.getElementById("account-load");
const accountSaveButton = document.getElementById("account-save");
const accountStatus = document.getElementById("account-status");
const accountSourceSelect = document.getElementById("account-source");
const dsqlStatus = document.getElementById("dsql-status");
const printResult = document.getElementById("print-result");
const printSuccessButton = document.getElementById("print-success");
const printFailureButton = document.getElementById("print-failure");
const printStatus = document.getElementById("print-status");
const pageSizeSelect = document.getElementById("page-size");
const customSizeSection = document.getElementById("custom-size");

const fields = {
  name: document.getElementById("account-name"),
  routingNumber: document.getElementById("routing-number"),
  accountNumber: document.getElementById("account-number"),
  micrStyle: document.getElementById("micr-style"),
  ownerName: document.getElementById("owner-name"),
  ownerAddress: document.getElementById("owner-address"),
  bankName: document.getElementById("bank-name"),
  bankAddress: document.getElementById("bank-address"),
  fractionalRouting: document.getElementById("fractional-routing"),
  lastCheckNumber: document.getElementById("last-check-number"),
  firstCheckNumber: document.getElementById("first-check-number"),
  totalChecks: document.getElementById("total-checks"),
  checksPerPage: document.getElementById("checks-per-page"),
  customWidth: document.getElementById("custom-width"),
  customHeight: document.getElementById("custom-height"),
};

let latestRun = null;
let dsqlAccounts = new Map();

function setStatus(target, message, isError = false) {
  target.textContent = message;
  target.classList.toggle("error", isError);
}

function getAccountPayload() {
  return {
    owner_name: fields.ownerName.value.trim(),
    owner_address: fields.ownerAddress.value.trim(),
    bank_name: fields.bankName.value.trim(),
    bank_address: fields.bankAddress.value.trim(),
    fractional_routing: fields.fractionalRouting.value.trim(),
    routing_number: fields.routingNumber.value.trim(),
    account_number: fields.accountNumber.value.trim(),
    micr_style: fields.micrStyle.value,
    last_check_number: Number.parseInt(fields.lastCheckNumber.value, 10) || 1,
  };
}

function applyAccount(data) {
  fields.routingNumber.value = data.routing_number || "";
  fields.accountNumber.value = data.account_number || "";
  fields.micrStyle.value = data.micr_style || "A";
  fields.ownerName.value = data.owner_name || "";
  fields.ownerAddress.value = data.owner_address || "";
  fields.bankName.value = data.bank_name || "";
  fields.bankAddress.value = data.bank_address || "";
  fields.fractionalRouting.value = data.fractional_routing || "";
  fields.lastCheckNumber.value = data.last_check_number || 1;
}

function applyDsqlAccount(data) {
  fields.routingNumber.value = data.routing || "";
  fields.accountNumber.value = data.account || "";
  fields.micrStyle.value = "A";
  fields.ownerName.value = [data.company_name_1, data.company_name_2].filter(Boolean).join("\n");
  fields.ownerAddress.value = [data.company_address_1, data.company_address_2].filter(Boolean).join("\n");
  fields.bankName.value = [data.bank_name_1, data.bank_name_2].filter(Boolean).join("\n");
  fields.bankAddress.value = [data.bank_address_1, data.bank_address_2].filter(Boolean).join("\n");
  fields.fractionalRouting.value = data.bank_fractional || "";
  const nextCheckNumber = Number.parseInt(data.next_check_number, 10) || 1;
  const lastCheckNumber = Math.max(nextCheckNumber - 1, 1);
  fields.lastCheckNumber.value = lastCheckNumber;
  fields.firstCheckNumber.value = Math.max(nextCheckNumber, 1);
}

async function refreshAccounts() {
  const source = accountSourceSelect.value;
  accountSelect.innerHTML = '<option value="">Select an account</option>';
  if (source === "dsql") {
    try {
      const response = await fetch("/api/dsql/accounts");
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Failed to load DSQL accounts.");
      }
      dsqlAccounts = new Map(
        payload.accounts.map((account) => [String(account.bank_account_id), account])
      );
      payload.accounts.forEach((account) => {
        const option = document.createElement("option");
        option.value = String(account.bank_account_id);
        option.textContent = account.name || `Account ${account.bank_account_id}`;
        accountSelect.appendChild(option);
      });
      accountLoadButton.disabled = payload.accounts.length === 0;
      setStatus(dsqlStatus, "Loaded DSQL accounts.");
    } catch (error) {
      accountLoadButton.disabled = true;
      setStatus(dsqlStatus, error.message || "Unable to load DSQL accounts.", true);
    }
  } else {
    try {
      const response = await fetch("/api/accounts");
      if (!response.ok) throw new Error("Failed to load accounts.");
      const payload = await response.json();
      payload.accounts.forEach((name) => {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        accountSelect.appendChild(option);
      });
      accountLoadButton.disabled = payload.accounts.length === 0;
      setStatus(dsqlStatus, "");
    } catch (error) {
      accountLoadButton.disabled = true;
      setStatus(accountStatus, "Unable to load accounts.", true);
    }
  }
}

async function loadAccount(name) {
  if (!name) {
    setStatus(accountStatus, "Select an account to load.", true);
    return;
  }
  if (accountSourceSelect.value === "dsql") {
    const account = dsqlAccounts.get(String(name));
    if (!account) {
      setStatus(accountStatus, "DSQL account not found.", true);
      return;
    }
    fields.name.value = account.name || "";
    applyDsqlAccount(account);
    setStatus(accountStatus, `Loaded DSQL account "${account.name}".`);
    return;
  }
  try {
    const response = await fetch(`/api/accounts/${encodeURIComponent(name)}`);
    if (!response.ok) throw new Error("Account not found.");
    const payload = await response.json();
    fields.name.value = payload.name;
    applyAccount(payload.data || {});
    setStatus(accountStatus, `Loaded account "${payload.name}".`);
  } catch (error) {
    setStatus(accountStatus, "Unable to load account.", true);
  }
}

accountLoadButton.addEventListener("click", () => {
  loadAccount(accountSelect.value);
});

accountSaveButton.addEventListener("click", async () => {
  if (accountSourceSelect.value === "dsql") {
    setStatus(accountStatus, "DSQL accounts are managed in the database.", true);
    return;
  }
  const name = fields.name.value.trim();
  if (!name) {
    setStatus(accountStatus, "Add an account name before saving.", true);
    return;
  }
  try {
    const response = await fetch("/api/accounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, data: getAccountPayload() }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to save account.");
    }
    await refreshAccounts();
    accountSelect.value = name;
    setStatus(accountStatus, `Saved account "${payload.name}".`);
  } catch (error) {
    setStatus(accountStatus, error.message || "Unable to save account.", true);
  }
});

pageSizeSelect.addEventListener("change", () => {
  const isCustom = pageSizeSelect.value === "custom";
  customSizeSection.hidden = !isCustom;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const source = accountSourceSelect.value;
  const accountName = accountSelect.value || fields.name.value.trim();
  if (!accountName) {
    setStatus(printStatus, "Select or save an account first.", true);
    printResult.hidden = false;
    return;
  }

  const payload = new FormData();
  payload.append("account", accountName);
  payload.append("account_source", source);
  payload.append("first_check_number", fields.firstCheckNumber.value);
  payload.append("total_checks", fields.totalChecks.value);
  payload.append("checks_per_page", fields.checksPerPage.value);
  payload.append("page_size", pageSizeSelect.value);
  payload.append("custom_width", fields.customWidth.value);
  payload.append("custom_height", fields.customHeight.value);

  try {
    const response = await fetch("/generate-blank", {
      method: "POST",
      body: payload,
    });
    if (!response.ok) {
      const errorPayload = await response.json();
      throw new Error(errorPayload.error || "Unable to generate blank checks.");
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "check_pdfs.zip";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);

    latestRun = {
      accountName,
      accountSource: source,
      lastCheckNumber:
        (Number.parseInt(fields.firstCheckNumber.value, 10) || 1) +
        (Number.parseInt(fields.totalChecks.value, 10) || 1) -
        1,
    };
    printResult.hidden = false;
    setStatus(printStatus, "PDFs generated (micr/nomicr). Confirm whether the print succeeded.");
  } catch (error) {
    printResult.hidden = false;
    setStatus(printStatus, error.message || "Unable to generate blank checks.", true);
  }
});

printSuccessButton.addEventListener("click", async () => {
  if (!latestRun) return;
  try {
    const endpoint =
      latestRun.accountSource === "dsql"
        ? `/api/dsql/accounts/${encodeURIComponent(latestRun.accountName)}/next-check`
        : `/api/accounts/${encodeURIComponent(latestRun.accountName)}/last-check`;
    const payloadKey = latestRun.accountSource === "dsql" ? "next_check_number" : "last_check_number";
    const payloadValue =
      latestRun.accountSource === "dsql" ? latestRun.lastCheckNumber + 1 : latestRun.lastCheckNumber;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ [payloadKey]: payloadValue }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Unable to update check number.");
    }
    const updatedValue = payload.last_check_number ?? payload.next_check_number;
    if (latestRun.accountSource === "dsql") {
      const lastCheckNumber = Math.max(updatedValue - 1, 1);
      fields.lastCheckNumber.value = lastCheckNumber;
      fields.firstCheckNumber.value = Math.max(updatedValue, 1);
    } else {
      fields.lastCheckNumber.value = updatedValue;
      fields.firstCheckNumber.value = updatedValue + 1;
    }
    setStatus(printStatus, "Marked successful. Account numbering updated.");
  } catch (error) {
    setStatus(printStatus, error.message || "Unable to update check number.", true);
  }
});

printFailureButton.addEventListener("click", () => {
  latestRun = null;
  setStatus(printStatus, "Marked unsuccessful. Account numbering unchanged.");
});

pageSizeSelect.dispatchEvent(new Event("change"));
accountSourceSelect.addEventListener("change", () => {
  const isDsql = accountSourceSelect.value === "dsql";
  fields.name.disabled = isDsql;
  accountSaveButton.disabled = isDsql;
  setStatus(accountStatus, "");
  refreshAccounts();
});
refreshAccounts();
