import {
  clearSession,
  getCurrentUser,
  getToken,
  loginRequest,
  saveSession,
} from "./api.js";
import { renderHomeMenu } from "./menus/home.js";
import { renderInputMutasiMenu } from "./menus/inputMutasi.js";
import { renderInputStrukMenu } from "./menus/inputStruk.js?v=4";
import { renderRekonsiliasiMenu } from "./menus/rekonsiliasi.js";

const MENU_REGISTRY = {
  home: {
    label: "Home",
    render: renderHomeMenu,
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1h-5.5v-6h-5v6H4a1 1 0 0 1-1-1v-9.5Z" /></svg>`,
  },
  input_struk: {
    label: "Input Struk",
    render: renderInputStrukMenu,
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h4M7 3h10a2 2 0 0 1 2 2v16l-3-2-2 2-2-2-2 2-2-2-3 2V5a2 2 0 0 1 2-2Z" /></svg>`,
  },
  input_mutasi: {
    label: "Input Mutasi",
    render: renderInputMutasiMenu,
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></svg>`,
  },
  rekonsiliasi: {
    label: "Rekonsiliasi",
    render: renderRekonsiliasiMenu,
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0 1 12 2.944a11.955 11.955 0 0 1-8.618 3.04A12.02 12.02 0 0 0 3 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016Z" /></svg>`,
  },
};

const ROLE_STYLES = {
  management: "bg-amber-100 text-amber-800",
  finance: "bg-blue-100 text-blue-800",
  staff: "bg-violet-100 text-violet-800",
};

const appHeaderEl = document.getElementById("app-header");
const logoutBtn = document.getElementById("logout-btn");

const loginSection = document.getElementById("login-section");
const appSection = document.getElementById("app-section");
const loginForm = document.getElementById("login-form");
const loginUsernameInput = document.getElementById("login-username");
const loginPasswordInput = document.getElementById("login-password");
const loginErrorEl = document.getElementById("login-error");

const desktopNavEl = document.getElementById("desktop-nav");
const mobileNavEl = document.getElementById("mobile-nav");
const userAvatarEl = document.getElementById("user-avatar");
const userNameEl = document.getElementById("user-name");
const userAccessNoteEl = document.getElementById("user-access-note");
const userRolePillEl = document.getElementById("user-role-pill");
const menuContentEl = document.getElementById("menu-content");

let activeMenu = null;

function renderNavigation(allowedMenus) {
  desktopNavEl.innerHTML = "";
  mobileNavEl.innerHTML = "";

  allowedMenus.forEach((menuKey) => {
    const meta = MENU_REGISTRY[menuKey];
    if (!meta) return;
    const isActive = activeMenu === menuKey;

    // Desktop pill button
    const deskBtn = document.createElement("button");
    deskBtn.type = "button";
    deskBtn.className = isActive
      ? "inline-flex items-center gap-2 h-9 px-3.5 rounded-xl text-xs font-semibold bg-white text-slate-900 shadow-xs transition"
      : "inline-flex items-center gap-2 h-9 px-3.5 rounded-xl text-xs font-semibold text-slate-600 hover:text-slate-900 transition";
    deskBtn.innerHTML = `${meta.icon}<span>${meta.label}</span>`;
    deskBtn.addEventListener("click", () => navigateTo(menuKey));
    desktopNavEl.appendChild(deskBtn);
  });

  // Mobile bottom navigation
  const grid = document.createElement("div");
  grid.className = `grid h-16 max-w-lg mx-auto`;
  grid.style.gridTemplateColumns = `repeat(${Math.max(allowedMenus.length, 1)}, minmax(0, 1fr))`;

  allowedMenus.forEach((menuKey) => {
    const meta = MENU_REGISTRY[menuKey];
    if (!meta) return;
    const isActive = activeMenu === menuKey;

    const mobBtn = document.createElement("button");
    mobBtn.type = "button";
    mobBtn.className = isActive
      ? "flex flex-col items-center justify-center gap-1 text-slate-900 transition"
      : "flex flex-col items-center justify-center gap-1 text-slate-500 hover:text-slate-900 transition";
    mobBtn.innerHTML = `
      <span class="w-11 h-7 rounded-full flex items-center justify-center transition ${isActive ? "bg-slate-900 text-white" : ""}">
        ${meta.icon}
      </span>
      <span class="text-[11px] font-semibold leading-none">${meta.label}</span>
    `;
    mobBtn.addEventListener("click", () => navigateTo(menuKey));
    grid.appendChild(mobBtn);
  });

  mobileNavEl.appendChild(grid);
}

async function navigateTo(menuKey) {
  const user = getCurrentUser();
  const menu = MENU_REGISTRY[menuKey];
  if (!user || !menu || !user.allowed_menus.includes(menuKey)) return;

  activeMenu = menuKey;
  renderNavigation(user.allowed_menus);

  menuContentEl.innerHTML = `
    <div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center max-w-xl mx-auto text-sm text-slate-400">
      Memuat halaman...
    </div>
  `;

  try {
    await menu.render(menuContentEl, {
      user,
      navigateTo,
      onUnauthorized: updateAuthUI,
    });
  } catch (err) {
    menuContentEl.innerHTML = `
      <div class="rounded-3xl bg-rose-50 border border-rose-200 p-6 text-center max-w-xl mx-auto text-sm font-medium text-rose-700">
        ${err.message}
      </div>
    `;
  }
}

function updateAuthUI() {
  const token = getToken();
  const user = getCurrentUser();

  if (!token || !user) {
    appHeaderEl.classList.add("hidden");
    loginSection.classList.remove("hidden");
    appSection.classList.add("hidden");
    mobileNavEl.classList.add("hidden");
    return;
  }

  appHeaderEl.classList.remove("hidden");
  loginSection.classList.add("hidden");
  appSection.classList.remove("hidden");
  mobileNavEl.classList.remove("hidden");

  userAvatarEl.textContent = user.username.slice(0, 2).toUpperCase();
  userNameEl.textContent = `${user.full_name} (@${user.username})`;
  userAccessNoteEl.textContent = `Akses menu: ${user.allowed_menus.map((m) => MENU_REGISTRY[m]?.label || m).join(", ")}`;

  const roleClass = ROLE_STYLES[user.role] || "bg-slate-100 text-slate-800";
  userRolePillEl.className = `inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-bold uppercase tracking-wide shrink-0 ${roleClass}`;
  userRolePillEl.textContent = user.role;

  const menus = user.allowed_menus || [];
  if (!activeMenu || !menus.includes(activeMenu)) {
    activeMenu = menus[0] || null;
  }

  if (activeMenu) {
    navigateTo(activeMenu);
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginErrorEl.classList.add("hidden");

  try {
    const data = await loginRequest(loginUsernameInput.value.trim(), loginPasswordInput.value);
    saveSession(data.access_token, data.user);
    loginForm.reset();
    updateAuthUI();
  } catch (err) {
    loginErrorEl.textContent = err.message;
    loginErrorEl.classList.remove("hidden");
  }
});

document.querySelectorAll(".demo-fill-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    loginUsernameInput.value = btn.dataset.demoUser || "";
    loginPasswordInput.value = btn.dataset.demoPass || "";
    loginUsernameInput.focus();
  });
});

logoutBtn.addEventListener("click", () => {
  clearSession();
  activeMenu = null;
  updateAuthUI();
});

updateAuthUI();
