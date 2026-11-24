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

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatTokenCount(value) {
  return Number(value || 0).toLocaleString("id-ID");
}

export function formatAiCostIdr(idr) {
  const num = Number(idr || 0);
  if (num <= 0) return "Rp0";
  if (num < 1) {
    return `Rp${num.toLocaleString("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (num < 100) {
    return `Rp${num.toLocaleString("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
  }
  return `Rp${Math.round(num).toLocaleString("id-ID")}`;
}

export function formatAiCostUsd(usd) {
  const num = Number(usd || 0);
  if (num <= 0) return "$0";
  if (num < 0.0001) return `$${num.toFixed(6)}`;
  return `$${num.toFixed(5)}`;
}

export function renderAiCostCard(aiUsage, { contextLabel = "Penggunaan Token AI" } = {}) {
  if (!aiUsage) return "";
  if (aiUsage.used_ai === false) {
    return `
      <div class="rounded-2xl bg-emerald-50/80 border border-emerald-200/90 px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-2 text-xs">
        <div class="flex items-center gap-2">
          <span class="px-2 py-0.5 rounded-md bg-emerald-100 text-emerald-800 text-[10px] font-bold uppercase tracking-wide">0 Token AI</span>
          <span class="font-semibold text-emerald-900">${escapeHtml(contextLabel)} · ${escapeHtml(aiUsage.model || "Deterministik")}</span>
        </div>
        <span class="font-mono font-bold text-emerald-800">Biaya Rp0</span>
      </div>
    `;
  }

  const promptTok = Number(aiUsage.prompt_tokens || 0);
  const compTok = Number(aiUsage.completion_tokens || 0);
  const totalTok = Number(aiUsage.total_tokens || promptTok + compTok);
  const costIdr = Number(aiUsage.cost_idr || 0);
  const costUsd = Number(aiUsage.cost_usd || 0);
  const latencyMs = Number(aiUsage.latency_ms || 0);
  const pages = Number(aiUsage.pages_processed || 0);

  return `
    <div class="rounded-2xl bg-indigo-50/70 border border-indigo-200/80 px-3.5 py-2.5 space-y-1.5 text-xs">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-1.5 min-w-0">
          <span class="px-2 py-0.5 rounded-md bg-indigo-100 text-indigo-800 text-[10px] font-bold uppercase tracking-wide">${escapeHtml(contextLabel)}</span>
          <span class="font-mono text-[11px] font-semibold text-slate-800 truncate">${escapeHtml(aiUsage.model || "-")}</span>
        </div>
        <div class="flex items-center gap-1.5 font-mono shrink-0">
          <span class="font-extrabold text-indigo-900">${escapeHtml(formatAiCostIdr(costIdr))}</span>
          <span class="text-[11px] text-indigo-600">(${escapeHtml(formatAiCostUsd(costUsd))})</span>
        </div>
      </div>
      <div class="flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-600">
        <span class="font-mono">
          Input ${formatTokenCount(promptTok)} · Output ${formatTokenCount(compTok)} · <strong>Total ${formatTokenCount(totalTok)} token</strong>
        </span>
        <span class="font-mono text-slate-500">
          ${pages > 1 ? `${pages} hal · ` : ""}${latencyMs > 0 ? `${latencyMs} ms` : ""}
        </span>
      </div>
    </div>
  `;
}

export function renderAiCostRowBadge(aiUsage) {
  if (!aiUsage) return "";
  const totalTok = Number(aiUsage.total_tokens || 0);
  const costIdr = Number(aiUsage.cost_idr || 0);
  const model = String(aiUsage.model || "");
  if (totalTok <= 0 && !model) return "";
  if (totalTok <= 0 && model.toLowerCase().includes("deterministik")) {
    return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 font-mono text-[10px] font-semibold">Rp0 · 0 tok</span>`;
  }
  if (totalTok <= 0) return "";
  return `<span title="${escapeHtml(model)}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 font-mono text-[10px] font-semibold">${escapeHtml(formatAiCostIdr(costIdr))} · ${formatTokenCount(totalTok)} tok</span>`;
}
