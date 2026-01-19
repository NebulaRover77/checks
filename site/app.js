const form = document.getElementById("check-form");
const resetButton = document.getElementById("reset");
const pageSizeSelect = document.getElementById("page-size");
const customSizeSection = document.getElementById("custom-size");

const preview = {
  payee: document.getElementById("preview-payee"),
  amount: document.getElementById("preview-amount"),
  words: document.getElementById("preview-words"),
  date: document.getElementById("preview-date"),
  memo: document.getElementById("preview-memo"),
  layout: document.getElementById("preview-layout"),
};

const presetSelect = document.getElementById("preset-select");
const presetLoadButton = document.getElementById("preset-load");
const presetNameInput = document.getElementById("preset-name");
const presetSaveButton = document.getElementById("preset-save");
const presetStatus = document.getElementById("preset-status");

const defaults = {
  payee: "",
  amount: "0.00",
  date: "01/19/2024",
  memo: "",
  page_size: "triple",
  custom_width: "8.5",
  custom_height: "11",
  checks_per_page: "3",
  position: "1",
};

const smallNumbers = [
  "Zero",
  "One",
  "Two",
  "Three",
  "Four",
  "Five",
  "Six",
  "Seven",
  "Eight",
  "Nine",
  "Ten",
  "Eleven",
  "Twelve",
  "Thirteen",
  "Fourteen",
  "Fifteen",
  "Sixteen",
  "Seventeen",
  "Eighteen",
  "Nineteen",
];

const tens = [
  "",
  "",
  "Twenty",
  "Thirty",
  "Forty",
  "Fifty",
  "Sixty",
  "Seventy",
  "Eighty",
  "Ninety",
];

function numberToWords(value) {
  if (value < 20) return smallNumbers[value];
  if (value < 100) {
    const whole = Math.floor(value / 10);
    const remainder = value % 10;
    return remainder ? `${tens[whole]} ${smallNumbers[remainder]}` : tens[whole];
  }
  if (value < 1000) {
    const whole = Math.floor(value / 100);
    const remainder = value % 100;
    const remainderWords = remainder ? ` ${numberToWords(remainder)}` : "";
    return `${smallNumbers[whole]} Hundred${remainderWords}`;
  }
  if (value < 10000) {
    const whole = Math.floor(value / 1000);
    const remainder = value % 1000;
    const remainderWords = remainder ? ` ${numberToWords(remainder)}` : "";
    return `${smallNumbers[whole]} Thousand${remainderWords}`;
  }
  return "";
}

function formatAmount(rawAmount) {
  const amount = Number.parseFloat(rawAmount || "0");
  if (Number.isNaN(amount)) {
    return { formatted: "0.00", words: "Zero and 00/100" };
  }

  const dollars = Math.floor(amount);
  const cents = Math.round((amount - dollars) * 100);
  const dollarsWords = numberToWords(dollars) || "";
  const centsValue = String(cents).padStart(2, "0");
  return {
    formatted: amount.toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }),
    words: `${dollarsWords} and ${centsValue}/100`,
  };
}

function updatePreview() {
  const data = new FormData(form);
  const payee = data.get("payee")?.toString() || "";
  const amount = data.get("amount")?.toString() || "0";
  const date = data.get("date")?.toString() || "";
  const memo = data.get("memo")?.toString() || "";
  const checksPerPage = data.get("checks_per_page")?.toString() || "1";

  const amountData = formatAmount(amount);

  preview.payee.textContent = payee || "—";
  preview.amount.textContent = amountData.formatted;
  preview.words.textContent = amountData.words;
  preview.date.textContent = date || "—";
  preview.memo.textContent = memo || "—";
  preview.layout.textContent = `${checksPerPage} per page`;
}

function setStatus(message, isError = false) {
  if (!presetStatus) return;
  presetStatus.textContent = message;
  presetStatus.classList.toggle("error", isError);
}

function getFormValues() {
  const data = new FormData(form);
  const values = {};
  data.forEach((value, key) => {
    values[key] = value.toString();
  });
  return values;
}

function applyPreset(values) {
  Object.entries({ ...defaults, ...values }).forEach(([key, value]) => {
    if (form.elements[key]) {
      form.elements[key].value = value;
    }
  });
  pageSizeSelect.dispatchEvent(new Event("change"));
  updatePreview();
}

async function refreshPresets() {
  if (!presetSelect) return;
  try {
    const response = await fetch("/api/settings");
    if (!response.ok) throw new Error("Failed to load presets.");
    const payload = await response.json();
    presetSelect.innerHTML = '<option value="">Select a preset</option>';
    payload.settings.forEach((name) => {
      const option = document.createElement("option");
      option.value = name;
      option.textContent = name;
      presetSelect.appendChild(option);
    });
    presetLoadButton.disabled = payload.settings.length === 0;
  } catch (error) {
    presetLoadButton.disabled = true;
    setStatus("Unable to load presets right now.", true);
  }
}

form.addEventListener("input", updatePreview);

resetButton.addEventListener("click", () => {
  Object.entries(defaults).forEach(([key, value]) => {
    form.elements[key].value = value;
  });
  pageSizeSelect.dispatchEvent(new Event("change"));
  updatePreview();
});

pageSizeSelect.addEventListener("change", () => {
  const isCustom = pageSizeSelect.value === "custom";
  customSizeSection.hidden = !isCustom;
});

pageSizeSelect.dispatchEvent(new Event("change"));
updatePreview();
refreshPresets();

if (presetLoadButton) {
  presetLoadButton.addEventListener("click", async () => {
    const selected = presetSelect.value;
    if (!selected) {
      setStatus("Select a preset to load.", true);
      return;
    }
    try {
      const response = await fetch(`/api/settings/${encodeURIComponent(selected)}`);
      if (!response.ok) throw new Error("Preset not found.");
      const payload = await response.json();
      applyPreset(payload.data || {});
      setStatus(`Loaded preset "${payload.name}".`);
    } catch (error) {
      setStatus("Unable to load preset.", true);
    }
  });
}

if (presetSaveButton) {
  presetSaveButton.addEventListener("click", async () => {
    const name = presetNameInput.value.trim();
    if (!name) {
      setStatus("Add a preset name before saving.", true);
      return;
    }
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, data: getFormValues() }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Unable to save preset.");
      }
      await refreshPresets();
      presetSelect.value = name;
      setStatus(`Saved preset "${payload.name}".`);
    } catch (error) {
      setStatus(error.message || "Unable to save preset.", true);
    }
  });
}
