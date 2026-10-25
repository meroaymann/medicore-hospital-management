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
    // Success/info messages disappear after 5 seconds; errors and warnings stay until closed
  if (flash.classList.contains("flash-success") || flash.classList.contains("flash-info")) {
    setTimeout(remove, 5000);
  }
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

// ================= MOBILE SIDEBAR =================
const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("overlay");
const menuBtn = document.getElementById("menuBtn");
const sidebarClose = document.getElementById("sidebarClose");

function openSidebar() {
  if (!sidebar) return;
  sidebar.classList.add("open");
  overlay.classList.add("show");
}

function closeSidebar() {
  if (!sidebar) return;
  sidebar.classList.remove("open");
  overlay.classList.remove("show");
}

if (menuBtn) menuBtn.addEventListener("click", openSidebar);
if (sidebarClose) sidebarClose.addEventListener("click", closeSidebar);
if (overlay) overlay.addEventListener("click", closeSidebar);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeSidebar();
});

// ================= SHORTCUT: press "/" to search =================
document.addEventListener("keydown", (e) => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (e.key === "/" && !typing) {
    const searchBox = document.querySelector(".search-form input");
    if (searchBox) {
      e.preventDefault();
      searchBox.focus();
    }
  }
});

// ================= CONFIRM BEFORE SUBMITTING =================
// Any <form data-confirm="..."> asks before it's sent
document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (!confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// ================= PREVENT DOUBLE SUBMIT =================
// After a POST form is sent, disable its button so a double-click can't send it twice
document.querySelectorAll('form[method="post" i]').forEach((form) => {
  form.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return; // e.g. the user clicked "Cancel" on a confirmation
    form.querySelectorAll('button[type="submit"]').forEach((btn) => {
      btn.disabled = true;
    });
  });
});

// If the user comes back with the browser's Back button, re-enable the buttons
window.addEventListener("pageshow", (e) => {
  if (e.persisted) {
    document.querySelectorAll('button[type="submit"]:disabled').forEach((btn) => {
      btn.disabled = false;
    });
  }
});