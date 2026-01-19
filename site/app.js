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
