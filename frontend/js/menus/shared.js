import { apiFetch } from "../api.js";

/**
 * Render halaman placeholder dengan gaya referensi card D:\Project\TugasAkhirRework\templates\index.html
 */
export function renderPlaceholderCard({ badgeText, title, message, theme, iconSvg, onBackHome = null }) {
  const themeMap = {
    blue: {
      iconBox: "bg-blue-50 text-blue-600",
      badge: "bg-blue-50 text-blue-700",
    },
    amber: {
      iconBox: "bg-amber-50 text-amber-600",
      badge: "bg-amber-50 text-amber-700",
    },
    emerald: {
      iconBox: "bg-emerald-50 text-emerald-600",
      badge: "bg-emerald-50 text-emerald-700",
    },
    indigo: {
      iconBox: "bg-indigo-50 text-indigo-600",
      badge: "bg-indigo-50 text-indigo-700",
    },
  };

  const colors = themeMap[theme] || themeMap.blue;

  const wrapper = document.createElement("section");
  wrapper.className = "view-animate";
  wrapper.innerHTML = `
    <div class="rounded-3xl bg-white border border-slate-200/90 p-6 sm:p-10 text-center max-w-xl mx-auto shadow-2xs space-y-4">
      <div class="w-14 h-14 rounded-2xl ${colors.iconBox} mx-auto flex items-center justify-center">
        ${iconSvg}
      </div>
      <div class="space-y-1.5">
        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${colors.badge}">
          ${badgeText}
        </span>
        <h2 class="text-lg font-bold text-slate-900">${title}</h2>
        <p class="text-sm text-slate-500 leading-relaxed">${message}</p>
      </div>
      ${
        onBackHome
          ? `<button type="button" data-back-home class="inline-flex items-center justify-center h-10 px-4 rounded-xl text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition">Kembali ke Home</button>`
          : ""
      }
    </div>
  `;

  if (onBackHome) {
    wrapper.querySelector("[data-back-home]")?.addEventListener("click", onBackHome);
  }

  return wrapper;
}

export async function fetchMenuPlaceholder(endpoint, onUnauthorized) {
  const res = await apiFetch(endpoint, {}, onUnauthorized);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Akses ditolak");
  }
  return data.message;
}
