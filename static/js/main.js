// ================= DARK MODE =================
const themeToggle = document.getElementById("themeToggle");

function setTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  if (themeToggle) themeToggle.textContent = theme === "dark" ? "☀️" : "🌙";
  try { localStorage.setItem("theme", theme); } catch (e) {}
}

setTheme(document.documentElement.getAttribute("data-theme") || "light");

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    const now = document.documentElement.getAttribute("data-theme");
    setTheme(now === "dark" ? "light" : "dark");
  });
}

// ================= FLASH MESSAGES =================
document.querySelectorAll(".flash").forEach((flash) => {
  const remove = () => {
    flash.classList.add("hide");
    setTimeout(() => flash.remove(), 300);
  };
  const closeBtn = flash.querySelector(".flash-close");
  if (closeBtn) closeBtn.addEventListener("click", remove);
  setTimeout(remove, 5000); // disappear after 5 seconds
});

// ================= SHOW / HIDE PASSWORD =================
document.querySelectorAll(".toggle-password").forEach((btn) => {
  btn.addEventListener("click", () => {
    const input = btn.parentElement.querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    btn.textContent = show ? "🙈" : "👁";
    btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
  });
});