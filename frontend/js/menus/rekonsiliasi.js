import { apiFetch } from "../api.js";
import { fetchMenuPlaceholder } from "./shared.js";
import { formatTanggalId, monthLabel, round2 } from "./cashReportExcel.js";

/**
 * Menu Rekonsiliasi — konsisten dengan gaya UI/UX Input Struk & Input Mutasi:
 *   - Top bar terpisah dengan segmented view switcher (Rekonsiliasi | Cash Report)
 *   - Pemilih Rekening model pill cards (individual per rekening) & navigator Bulan
 *   - Ringkasan Saldo 4-kartu dengan status keseimbangan Bank vs Catatan
 *   - Tabel Desktop + Kartu Mobile untuk Mutasi Bank, Catatan Struk, dan Cash Report
 *   - Modal Match Manual / Split Admin, Catat Penyesuaian Mutasi, dan Galeri Lampiran
 */

const INPUT_CLS =
  "w-full h-10 px-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 disabled:bg-slate-100 disabled:text-slate-500 transition";

const TX_STATUS_BADGE = {
  BELUM_REKON: { cls: "bg-slate-100 text-slate-700", label: "Belum Rekon" },
  MUTASI_BELUM_ADA: { cls: "bg-amber-50 text-amber-800", label: "Mutasi Belum Ada" },
  SESUAI: { cls: "bg-emerald-50 text-emerald-700", label: "Sesuai Mutasi" },
  SELISIH_KODE_UNIK_ADMIN: { cls: "bg-blue-50 text-blue-700", label: "Cocok (Selisih Admin)" },
  PINDAH_BUKU_COCOK: { cls: "bg-indigo-50 text-indigo-700", label: "Pindah Buku Cocok" },
};

const MUTASI_STATUS_BADGE = {
  BELUM_REKON: { cls: "bg-slate-100 text-slate-700", label: "Belum Rekon" },
  BELUM_TERCATAT: { cls: "bg-amber-50 text-amber-800", label: "Belum Tercatat" },
  SESUAI: { cls: "bg-emerald-50 text-emerald-700", label: "Sesuai Struk" },
  SELISIH_KODE_UNIK_ADMIN: { cls: "bg-blue-50 text-blue-700", label: "Cocok (Selisih Admin)" },
  PINDAH_BUKU: { cls: "bg-indigo-50 text-indigo-700", label: "Pindah Buku" },
};

const MATCHED_TX_STATUSES = new Set(["SESUAI", "SELISIH_KODE_UNIK_ADMIN", "PINDAH_BUKU_COCOK"]);
const UNMATCHED_MUTASI_STATUSES = new Set(["BELUM_REKON", "BELUM_TERCATAT"]);

const ICON_DOWNLOAD = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>`;
const ICON_REFRESH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h5M20 20v-5h-5M5.5 9A7.5 7.5 0 0 1 19 6.5M18.5 15A7.5 7.5 0 0 1 5 17.5"/></svg>`;
const ICON_PHOTO = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path stroke-linecap="round" stroke-linejoin="round" d="m21 15-4.5-4.5a1.5 1.5 0 0 0-2.1 0L7 18"/></svg>`;
const ICON_LINK = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path stroke-linecap="round" stroke-linejoin="round" d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`;
const ICON_PLUS = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 5v14M5 12h14"/></svg>`;
const ICON_EDIT = `<svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 3.487a2.1 2.1 0 1 1 2.97 2.97L7.5 18.79 3 20l1.21-4.5L16.862 3.487Z"/></svg>`;
const ICON_TRASH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/></svg>`;
const ICON_SEARCH = `<svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>`;
const ICON_CLOSE = `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>`;

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatRp(amount) {
  if (amount === null || amount === undefined || amount === "") return "-";
  const n = round2(amount);
  const hasCents = Math.abs(n - Math.round(n)) > 1e-6;
  const formatted = Math.abs(n).toLocaleString("id-ID", {
    minimumFractionDigits: hasCents ? 2 : 0,
    maximumFractionDigits: hasCents ? 2 : 0,
  });
  return `${n < 0 ? "-" : ""}Rp${formatted}`;
}

function parseError(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail?.message) return data.detail.message;
  return data.message || fallback;
}

async function apiJson(path, options = {}, onUnauthorized = null) {
  const res = await apiFetch(path, options, onUnauthorized);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = new Error(parseError(data, `Gagal memproses ${path}`));
    err.status = res.status;
    throw err;
  }
  return data;
}

function dateDistanceDays(a, b) {
  const da = Date.parse(`${a}T00:00:00Z`);
  const db = Date.parse(`${b}T00:00:00Z`);
  if (!Number.isFinite(da) || !Number.isFinite(db)) return 999;
  return Math.abs(da - db) / 86400000;
}

/* ------------------------------------------------------------------ */

export async function renderRekonsiliasiMenu(container, { onUnauthorized }) {
  await fetchMenuPlaceholder("/rekonsiliasi", onUnauthorized);

  const state = {
    rekening: [],
    kategori: [],
    months: [],
    activity: {},
    rekeningId: null,
    monthKey: null,
    saldoAwalManual: null,
    editingSaldo: false,
    view: "reconcile", // "reconcile" | "cash_report"
    reconSubTab: "mutasi", // "mutasi" | "struk"
    reconFilter: "all", // "all" | "unmatched" | "matched"
    reconSearch: "",
    reportSearch: "",
    report: null,
    loadingMeta: false,
    loadingReport: false,
    mutatingAction: false,
    downloading: false,
    error: "",
    notice: "",
    metaRequestId: 0,
    reportRequestId: 0,
  };

  const selectedRekening = () =>
    state.rekening.find((r) => String(r.id) === String(state.rekeningId)) || null;

  function computeEffectiveReport() {
    const base = state.report;
    if (!base) return null;
    if (state.saldoAwalManual === null) return base;

    const awal = round2(state.saldoAwalManual);
    let saldo = awal;
    const rows = base.rows.map((row) => {
      saldo = round2(saldo + Number(row.debet || 0) - Number(row.kredit || 0));
      return { ...row, saldo };
    });
    const subTotalDebet = round2(awal + Number(base.total_debet_transaksi || 0));
    const totalKredit = round2(base.total_kredit || 0);
    const sisaSaldo = round2(subTotalDebet - totalKredit);
    let selisihSaldo = null;
    let isBalanced = null;
    if (base.saldo_akhir_bank !== null && base.saldo_akhir_bank !== undefined) {
      selisihSaldo = round2(saldo - Number(base.saldo_akhir_bank));
      isBalanced = Math.abs(selisihSaldo) <= 0.01;
      if (isBalanced) selisihSaldo = 0;
    }

    return {
      ...base,
      saldo_awal: awal,
      is_saldo_manual: true,
      rows,
      sub_total_debet: subTotalDebet,
      sisa_saldo: sisaSaldo,
      saldo_akhir: saldo,
      selisih_saldo: selisihSaldo,
      is_balanced: isBalanced,
    };
  }

  function defaultRekeningId() {
    if (!state.rekening.length) return null;
    const score = (r) => {
      const act = state.activity[String(r.id)] || { tx_total: 0, mutasi_total: 0 };
      return Number(act.tx_total || 0) * 10 + Number(act.mutasi_total || 0);
    };
    return [...state.rekening].sort((a, b) => score(b) - score(a) || Number(a.id) - Number(b.id))[0].id;
  }

  function defaultMonthFor(rekId) {
    const act = state.activity[String(rekId)];
    if (act?.latest_month) return act.latest_month;
    return state.months[0] || null;
  }

  /* ------------------------- Render Sections ------------------------- */

  function renderTopBar(report) {
    const isCash = Boolean(selectedRekening()?.is_cash);
    const activeView = isCash ? "cash_report" : state.view;
    const unmatchedCount = report
      ? Number(report.summary?.mutasi_belum_tercatat || 0) +
        Number(report.summary?.mutasi_belum_rekon || 0) +
        Number(report.summary?.tx_unmatched || 0)
      : 0;
    const txCount = report ? Number(report.summary?.tx_total || 0) : 0;

    return `
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-lg font-bold text-slate-900 tracking-tight">Rekonsiliasi &amp; Cash Report</h2>
          <p class="text-xs text-slate-500">Cocokkan transaksi Struk dengan mutasi bank, catat penyesuaian, dan ekspor Cash Report Excel.</p>
        </div>
        <div class="inline-flex p-1 rounded-2xl bg-slate-200/75 self-start sm:self-auto">
          ${
            !isCash
              ? `<button
                  type="button"
                  data-switch-view="reconcile"
                  class="h-8 px-3.5 rounded-xl text-xs font-semibold transition inline-flex items-center gap-1.5 ${
                    activeView === "reconcile" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                  }"
                >
                  <span>Rekonsiliasi</span>
                  ${
                    unmatchedCount > 0
                      ? `<span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
                          activeView === "reconcile" ? "bg-amber-500 text-white" : "bg-amber-100 text-amber-800"
                        }">${unmatchedCount}</span>`
                      : report
                        ? `<span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold bg-emerald-100 text-emerald-700">✓</span>`
                        : ""
                  }
                </button>`
              : ""
          }
          <button
            type="button"
            data-switch-view="cash_report"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold transition inline-flex items-center gap-1.5 ${
              activeView === "cash_report" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            <span>Cash Report</span>
            <span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
              activeView === "cash_report" ? "bg-slate-900 text-white" : "bg-slate-300/80 text-slate-700"
            }">${txCount}</span>
          </button>
        </div>
      </div>
    `;
  }

  function renderControlCard(report) {
    const busy = state.loadingMeta || state.loadingReport || state.downloading || state.mutatingAction;
    const rek = selectedRekening();
    const isCash = Boolean(rek?.is_cash);
    const monthIdx = state.months.indexOf(state.monthKey);
    const hasOlderMonth = monthIdx >= 0 && monthIdx < state.months.length - 1;
    const hasNewerMonth = monthIdx > 0;
    const act = state.activity[String(state.rekeningId)] || { tx_per_month: {}, mutasi_per_month: {} };

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
        <!-- Selector Rekening (Segmented Pill Grid seperti Input Mutasi) -->
        <div class="space-y-2">
          <div class="flex flex-wrap items-center justify-between gap-2 px-1">
            <span class="text-xs font-bold text-slate-700">Pilih Rekening Perusahaan</span>
            <span class="text-[11px] text-slate-400">Cash Report &amp; rekonsiliasi dihitung terpisah per rekening</span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 p-1 rounded-2xl bg-slate-100">
            ${state.rekening
              .map((r) => {
                const active = String(r.id) === String(state.rekeningId);
                const rAct = state.activity[String(r.id)] || { tx_total: 0, mutasi_total: 0 };
                const totalItems = Number(rAct.tx_total || 0) + Number(rAct.mutasi_total || 0);
                return `
                  <button
                    type="button"
                    data-select-rekening="${esc(r.id)}"
                    ${busy ? "disabled" : ""}
                    class="px-3 py-2 rounded-xl text-left transition disabled:opacity-60 ${
                      active ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                    }"
                  >
                    <div class="flex items-center justify-between gap-1">
                      <p class="text-xs font-bold truncate">${esc(r.kode_akun)}</p>
                      ${
                        totalItems > 0
                          ? `<span class="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold ${
                              active ? "bg-slate-900 text-white" : "bg-slate-200/80 text-slate-600"
                            }">${totalItems}</span>`
                          : ""
                      }
                    </div>
                    <p class="font-mono text-[10px] truncate mt-0.5 ${active ? "text-slate-500" : "text-slate-400"}">
                      ${esc(r.is_cash ? "Kas Tunai" : r.no_rekening)}
                    </p>
                  </button>
                `;
              })
              .join("")}
          </div>
        </div>

        <!-- Navigator Periode & Tombol Aksi -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="flex items-center gap-1.5">
            <button
              type="button"
              data-month-nav="older"
              ${busy || !hasOlderMonth ? "disabled" : ""}
              title="Bulan sebelumnya"
              class="h-9 w-9 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 text-slate-700 font-bold text-sm flex items-center justify-center transition"
            >‹</button>
            <select data-filter-month ${busy ? "disabled" : ""} class="h-9 px-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs font-semibold text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition min-w-[200px]">
              ${state.months
                .map((key) => {
                  const txN = Number(act.tx_per_month?.[key] || 0);
                  const mutN = Number(act.mutasi_per_month?.[key] || 0);
                  const tags = [];
                  if (txN) tags.push(`${txN} struk`);
                  if (mutN) tags.push(`${mutN} mutasi`);
                  return `<option value="${esc(key)}" ${key === state.monthKey ? "selected" : ""}>${esc(monthLabel(key))}${tags.length ? ` (${tags.join(" · ")})` : ""}</option>`;
                })
                .join("")}
            </select>
            <button
              type="button"
              data-month-nav="newer"
              ${busy || !hasNewerMonth ? "disabled" : ""}
              title="Bulan berikutnya"
              class="h-9 w-9 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 text-slate-700 font-bold text-sm flex items-center justify-center transition"
            >›</button>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            ${
              !isCash
                ? `<button type="button" data-action="auto-run" ${busy ? "disabled" : ""} class="h-9 px-3 rounded-xl border border-blue-200 bg-blue-50/70 hover:bg-blue-100 text-blue-700 text-xs font-semibold inline-flex items-center gap-1.5 disabled:opacity-50 transition">
                    ${ICON_LINK}<span>Auto-Rekon</span>
                  </button>`
                : ""
            }
            <button type="button" data-action="refresh" ${busy ? "disabled" : ""} class="h-9 px-3 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold inline-flex items-center gap-1.5 disabled:opacity-50 transition">
              ${ICON_REFRESH}<span>Refresh</span>
            </button>
            <button type="button" data-action="download" ${busy || !report ? "disabled" : ""} class="h-9 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs inline-flex items-center gap-1.5 transition">
              ${ICON_DOWNLOAD}<span>${state.downloading ? "Mengunduh..." : "Download Excel"}</span>
            </button>
          </div>
        </div>

        ${
          state.error
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs font-semibold text-rose-700">${esc(state.error)}</div>`
            : ""
        }
        ${
          state.notice
            ? `<div class="rounded-2xl bg-emerald-50 border border-emerald-200 px-4 py-2.5 text-xs font-semibold text-emerald-800 flex items-center justify-between gap-2">
                <span>${esc(state.notice)}</span>
                <button type="button" data-dismiss-notice class="text-emerald-600 hover:text-emerald-900 font-bold">✕</button>
              </div>`
            : ""
        }
        ${
          report?.warnings?.length
            ? `<div class="rounded-2xl bg-amber-50 border border-amber-200 px-4 py-3 text-xs text-amber-900 space-y-1">
                <p class="font-bold">Perhatian Cakupan Mutasi:</p>
                <ul class="list-disc pl-4 space-y-0.5">${report.warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
              </div>`
            : ""
        }

        ${renderSummaryStrip(report)}
      </div>
    `;
  }

  function renderSummaryStrip(report) {
    if (state.loadingMeta || state.loadingReport) {
      return `
        <div class="rounded-2xl bg-slate-50 border border-slate-200/90 p-6 text-center text-xs text-slate-500">
          Memuat ringkasan saldo &amp; data rekonsiliasi…
        </div>
      `;
    }
    if (!report) {
      return `
        <div class="rounded-2xl bg-slate-50 border border-slate-200/90 p-6 text-center text-xs text-slate-500">
          Pilih rekening dan bulan untuk melihat ringkasan.
        </div>
      `;
    }

    const isCash = Boolean(report.rekening.is_cash);
    const hasBankEnd = !isCash && report.saldo_akhir_bank !== null && report.saldo_akhir_bank !== undefined;
    const isBalanced = Boolean(report.is_balanced);

    let statusPill = `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-slate-200/80 text-slate-700"><span class="w-2 h-2 rounded-full bg-slate-500"></span>${
      isCash ? "Kas Tunai (Tanpa Mutasi Bank)" : "Belum Ada Mutasi Bank"
    }</span>`;
    if (hasBankEnd) {
      statusPill = isBalanced
        ? `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800"><span class="w-2 h-2 rounded-full bg-emerald-600"></span>Saldo Cocok dengan Bank (Selisih Rp0)</span>`
        : `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-900"><span class="w-2 h-2 rounded-full bg-amber-600"></span>Selisih Catatan vs Bank: ${esc(formatRp(report.selisih_saldo))}</span>`;
    }

    const coverageText = isCash
      ? "Kas Operasional Perusahaan"
      : report.mutasi_periode_selesai
        ? `No. Rek ${report.rekening.no_rekening} · Mutasi ${formatTanggalId(report.mutasi_periode_mulai)} s.d. ${formatTanggalId(report.mutasi_periode_selesai)}`
        : `No. Rek ${report.rekening.no_rekening} · Belum ada batch mutasi pada ${report.month_label}`;

    const s = report.summary || {};
    const mutTotal = Number(s.mutasi_total || 0);
    const mutMatched = Number(s.mutasi_matched || 0);
    const mutPct = mutTotal > 0 ? Math.round((mutMatched / mutTotal) * 100) : 0;

    return `
      <div class="rounded-2xl bg-slate-50 border border-slate-200/90 p-4 space-y-3.5">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <span class="px-2.5 py-0.5 rounded-lg bg-slate-900 text-white text-xs font-bold">${esc(report.rekening.kode_akun)}</span>
              <span class="text-xs sm:text-sm font-bold text-slate-900 truncate">${esc(report.rekening.bank_lembaga)}</span>
              <span class="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 text-[11px] font-semibold">${esc(report.month_label)}</span>
            </div>
            <p class="text-[11px] text-slate-500 mt-1">${esc(coverageText)}</p>
          </div>
          ${statusPill}
        </div>

        <!-- 4 Kartu Saldo (Gaya Input Mutasi Step 2) -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-3 border-t border-slate-200/80">
          <div class="rounded-xl bg-white border border-slate-200/80 p-3 space-y-1">
            <div class="flex items-center justify-between gap-1">
              <p class="text-[11px] font-semibold text-slate-500">Saldo Awal</p>
              <div class="flex items-center gap-1.5">
                ${
                  state.saldoAwalManual !== null
                    ? `<button type="button" data-action="reset-saldo" class="text-[10px] font-bold text-blue-600 hover:text-blue-800">Otomatis</button>`
                    : ""
                }
                ${
                  !state.editingSaldo
                    ? `<button type="button" data-action="edit-saldo" class="inline-flex items-center gap-0.5 text-[10px] font-bold text-slate-600 hover:text-slate-900 px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200 transition">${ICON_EDIT}<span>Ubah</span></button>`
                    : ""
                }
              </div>
            </div>
            ${
              state.editingSaldo
                ? `<form data-saldo-form class="flex items-center gap-1 pt-0.5">
                    <input type="number" step="any" name="saldo_input" value="${esc(round2(report.saldo_awal))}" class="w-full h-8 px-2 rounded-lg border border-blue-400 bg-white font-mono text-xs font-bold text-slate-900 focus:outline-none" />
                    <button type="submit" class="h-8 px-2 rounded-lg bg-slate-900 text-white text-[10px] font-bold shrink-0">OK</button>
                    <button type="button" data-action="cancel-saldo" aria-label="Batal" class="h-8 w-7 rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-100 text-[10px] font-bold shrink-0">✕</button>
                  </form>`
                : `<p class="font-mono text-sm font-extrabold text-slate-900 tabular-nums">${formatRp(report.saldo_awal)}</p>
                   <p class="text-[10px] text-slate-400 truncate" title="${esc(report.auto_saldo_sumber)}">${
                     state.saldoAwalManual !== null ? "Diisi manual" : esc(report.auto_saldo_sumber)
                   }</p>`
            }
          </div>

          <div class="rounded-xl bg-white border border-emerald-200/80 p-3 space-y-1">
            <p class="text-[11px] font-semibold text-emerald-700">Total Masuk (Debet)</p>
            <p class="font-mono text-sm font-extrabold text-emerald-700 tabular-nums">+${formatRp(report.total_debet_transaksi)}</p>
            <p class="text-[10px] text-slate-400">Di luar Saldo Awal</p>
          </div>

          <div class="rounded-xl bg-white border border-rose-200/80 p-3 space-y-1">
            <p class="text-[11px] font-semibold text-rose-700">Total Keluar (Kredit)</p>
            <p class="font-mono text-sm font-extrabold text-rose-700 tabular-nums">-${formatRp(report.total_kredit)}</p>
            <p class="text-[10px] text-slate-400">${s.tx_total || 0} transaksi tercatat</p>
          </div>

          <div class="rounded-xl bg-slate-900 text-white p-3 space-y-1">
            <p class="text-[11px] font-semibold text-slate-300">Saldo Akhir Catatan</p>
            <p class="font-mono text-sm font-extrabold tabular-nums">${formatRp(report.saldo_akhir)}</p>
            <p class="text-[10px] text-slate-300 truncate">${
              hasBankEnd ? `Saldo Bank: ${formatRp(report.saldo_akhir_bank)}` : "Saldo awal + masuk − keluar"
            }</p>
          </div>
        </div>

        ${
          !isCash
            ? `<div class="pt-1 space-y-1.5">
                <div class="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <span class="text-slate-600 font-medium">
                    Mutasi Bank: <strong class="text-slate-900">${mutMatched}/${mutTotal}</strong> cocok
                    ${s.mutasi_belum_tercatat ? `· <span class="text-amber-700 font-semibold">${s.mutasi_belum_tercatat} belum tercatat</span>` : ""}
                    ${s.mutasi_belum_rekon ? `· <span class="text-slate-700 font-semibold">${s.mutasi_belum_rekon} belum rekon</span>` : ""}
                  </span>
                  <span class="text-slate-600 font-medium">
                    Catatan Struk: <strong class="text-slate-900">${s.tx_matched || 0}/${s.tx_total || 0}</strong> cocok
                  </span>
                </div>
                <div class="h-1.5 w-full rounded-full bg-slate-200 overflow-hidden">
                  <div class="h-full rounded-full ${mutPct === 100 && mutTotal > 0 ? "bg-emerald-500" : "bg-blue-600"} transition-all duration-300" style="width: ${mutPct}%"></div>
                </div>
              </div>`
            : ""
        }
      </div>
    `;
  }

  function filteredMutasiRows(report) {
    const q = state.reconSearch.trim().toLowerCase();
    return (report.mutasi_rows || []).filter((m) => {
      const isUnmatched = UNMATCHED_MUTASI_STATUSES.has(m.status_rekonsiliasi);
      if (state.reconFilter === "unmatched" && !isUnmatched) return false;
      if (state.reconFilter === "matched" && isUnmatched) return false;
      if (!q) return true;
      return `${m.id} ${m.tanggal} ${m.uraian} ${m.nominal} ${m.penyebab_selisih || ""}`.toLowerCase().includes(q);
    });
  }

  function filteredTxRows(report) {
    const q = state.reconSearch.trim().toLowerCase();
    return (report.rows || []).filter((tx) => {
      const isMatched = MATCHED_TX_STATUSES.has(tx.status_rekonsiliasi);
      if (state.reconFilter === "unmatched" && isMatched) return false;
      if (state.reconFilter === "matched" && !isMatched) return false;
      if (!q) return true;
      return `${tx.id} ${tx.tanggal_transaksi} ${tx.keterangan} ${tx.kategori} ${tx.total_mutasi}`.toLowerCase().includes(q);
    });
  }

  function renderReconcileBody(report) {
    if (state.reconSubTab === "mutasi") {
      const items = filteredMutasiRows(report);
      if (!items.length) {
        return `
          <div class="py-12 px-4 text-center space-y-1">
            <p class="text-sm font-semibold text-slate-700">Tidak ada baris mutasi bank</p>
            <p class="text-xs text-slate-400">Ubah filter status/pencarian atau unggah PDF mutasi di menu Input Mutasi.</p>
          </div>
        `;
      }
      return `
        <!-- Desktop Table -->
        <div class="hidden md:block overflow-x-auto">
          <table class="w-full text-left border-collapse text-xs">
            <thead>
              <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <th class="py-3 pl-5 pr-3">Tanggal</th>
                <th class="py-3 px-3">Uraian Mutasi Bank</th>
                <th class="py-3 px-3">Tipe</th>
                <th class="py-3 px-3 text-right">Nominal</th>
                <th class="py-3 px-3 text-right">Saldo Bank</th>
                <th class="py-3 px-3">Status</th>
                <th class="py-3 pl-3 pr-5 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
              ${items
                .map((m) => {
                  const badge = MUTASI_STATUS_BADGE[m.status_rekonsiliasi] || MUTASI_STATUS_BADGE.BELUM_REKON;
                  const isCr = m.tipe === "CR";
                  const unmatched = UNMATCHED_MUTASI_STATUSES.has(m.status_rekonsiliasi);
                  const firstMatch = (m.matches || [])[0];
                  return `
                    <tr class="hover:bg-slate-50/70 transition">
                      <td class="py-3.5 pl-5 pr-3 font-mono whitespace-nowrap align-top">
                        <p class="font-semibold text-slate-900">${esc(m.tanggal)}</p>
                        <p class="text-[11px] text-slate-400">${esc(m.waktu || "00:00:00")} · #M${m.id}</p>
                      </td>
                      <td class="py-3.5 px-3 max-w-[340px] align-top">
                        <p class="text-slate-900 font-medium leading-snug">${esc(m.uraian)}</p>
                        ${m.penyebab_selisih ? `<p class="text-[10px] font-semibold text-amber-700 mt-1">${esc(m.penyebab_selisih)}</p>` : ""}
                        ${
                          firstMatch
                            ? `<p class="text-[10px] font-semibold text-emerald-700 mt-1">Cocok dgn Transaksi #${esc(firstMatch.transaksi_internal_id)} (${esc(firstMatch.jenis_match)}${firstMatch.sumber_pencatatan === "PENYESUAIAN_MUTASI" ? " · Penyesuaian" : ""})</p>`
                            : ""
                        }
                      </td>
                      <td class="py-3.5 px-3 whitespace-nowrap align-top">
                        <span class="px-2 py-0.5 rounded-md font-mono text-[10px] font-bold ${isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}">${esc(m.tipe)}</span>
                      </td>
                      <td class="py-3.5 px-3 text-right font-mono text-sm font-extrabold tabular-nums whitespace-nowrap align-top ${isCr ? "text-emerald-700" : "text-slate-900"}">
                        ${isCr ? "+" : "-"}${formatRp(m.nominal)}
                      </td>
                      <td class="py-3.5 px-3 text-right font-mono tabular-nums whitespace-nowrap align-top text-slate-600">${formatRp(m.saldo)}</td>
                      <td class="py-3.5 px-3 whitespace-nowrap align-top">
                        <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                      </td>
                      <td class="py-3.5 pl-3 pr-5 text-right whitespace-nowrap align-top">
                        ${
                          unmatched
                            ? `<div class="inline-flex items-center gap-1.5">
                                <button type="button" data-match-mutasi="${m.id}" class="h-8 px-2.5 rounded-lg border border-blue-200 bg-blue-50/70 hover:bg-blue-100 text-blue-700 text-[11px] font-semibold inline-flex items-center gap-1 transition">
                                  ${ICON_LINK}<span>Cocokkan</span>
                                </button>
                                <button type="button" data-adjust-mutasi="${m.id}" class="h-8 px-2.5 rounded-lg bg-slate-900 hover:bg-slate-800 text-white text-[11px] font-semibold inline-flex items-center gap-1 transition">
                                  ${ICON_PLUS}<span>Penyesuaian</span>
                                </button>
                              </div>`
                            : firstMatch?.match_group_id
                              ? `<button type="button" data-unmatch-group="${esc(firstMatch.match_group_id)}" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold transition">
                                  Lepas Cocok
                                </button>`
                              : ""
                        }
                      </td>
                    </tr>
                  `;
                })
                .join("")}
            </tbody>
          </table>
        </div>

        <!-- Mobile Cards -->
        <div class="md:hidden divide-y divide-slate-100">
          ${items
            .map((m) => {
              const badge = MUTASI_STATUS_BADGE[m.status_rekonsiliasi] || MUTASI_STATUS_BADGE.BELUM_REKON;
              const isCr = m.tipe === "CR";
              const unmatched = UNMATCHED_MUTASI_STATUSES.has(m.status_rekonsiliasi);
              const firstMatch = (m.matches || [])[0];
              return `
                <article class="p-4 space-y-2.5">
                  <div class="flex items-start justify-between gap-2">
                    <div class="min-w-0">
                      <div class="flex flex-wrap items-center gap-1.5">
                        <span class="font-mono text-[11px] text-slate-400">#M${m.id}</span>
                        <span class="font-mono text-[11px] font-semibold text-slate-600">${esc(m.tanggal)}</span>
                        <span class="px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}">${esc(m.tipe)}</span>
                      </div>
                      <p class="text-xs font-semibold text-slate-900 mt-1">${esc(m.uraian)}</p>
                      ${firstMatch ? `<p class="text-[10px] font-semibold text-emerald-700 mt-0.5">Cocok dgn #${esc(firstMatch.transaksi_internal_id)}</p>` : ""}
                    </div>
                    <div class="text-right shrink-0">
                      <p class="font-mono text-sm font-extrabold tabular-nums ${isCr ? "text-emerald-700" : "text-slate-900"}">${isCr ? "+" : "-"}${formatRp(m.nominal)}</p>
                      <p class="font-mono text-[10px] text-slate-400">Saldo ${formatRp(m.saldo)}</p>
                    </div>
                  </div>
                  <div class="flex items-center justify-between gap-2 pt-1">
                    <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                    <div class="flex items-center gap-1.5">
                      ${
                        unmatched
                          ? `<button type="button" data-match-mutasi="${m.id}" class="h-8 px-2.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 text-[11px] font-semibold">Cocokkan</button>
                             <button type="button" data-adjust-mutasi="${m.id}" class="h-8 px-2.5 rounded-lg bg-slate-900 text-white text-[11px] font-semibold">Penyesuaian</button>`
                          : firstMatch?.match_group_id
                            ? `<button type="button" data-unmatch-group="${esc(firstMatch.match_group_id)}" class="h-8 px-2.5 rounded-lg border border-slate-200 text-slate-700 text-[11px] font-semibold">Lepas</button>`
                            : ""
                      }
                    </div>
                  </div>
                </article>
              `;
            })
            .join("")}
        </div>
      `;
    }

    // Sub-tab: Catatan Struk & Penyesuaian
    const items = filteredTxRows(report);
    if (!items.length) {
      return `
        <div class="py-12 px-4 text-center space-y-1">
          <p class="text-sm font-semibold text-slate-700">Tidak ada transaksi catatan internal</p>
          <p class="text-xs text-slate-400">Input transaksi di menu Input Struk atau catat Penyesuaian dari tab Mutasi Bank.</p>
        </div>
      `;
    }
    return `
      <!-- Desktop Table -->
      <div class="hidden md:block overflow-x-auto">
        <table class="w-full text-left border-collapse text-xs">
          <thead>
            <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
              <th class="py-3 pl-5 pr-3">Transaksi</th>
              <th class="py-3 px-3">Keterangan &amp; Kategori</th>
              <th class="py-3 px-3 text-right">Nominal</th>
              <th class="py-3 px-3">Lampiran</th>
              <th class="py-3 px-3">Status</th>
              <th class="py-3 pl-3 pr-5 text-right">Aksi</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">
            ${items
              .map((tx) => {
                const badge = TX_STATUS_BADGE[tx.status_rekonsiliasi] || TX_STATUS_BADGE.BELUM_REKON;
                const isMatched = MATCHED_TX_STATUSES.has(tx.status_rekonsiliasi);
                const firstMatch = (tx.matches || [])[0];
                const isPenyesuaian = tx.sumber_pencatatan === "PENYESUAIAN_MUTASI";
                const isDebet = tx.debet > 0;
                const amount = isDebet ? tx.debet : tx.kredit;
                return `
                  <tr class="hover:bg-slate-50/70 transition">
                    <td class="py-3.5 pl-5 pr-3 font-mono whitespace-nowrap align-top">
                      <p class="font-semibold text-slate-900">${esc(tx.tanggal_transaksi)}</p>
                      <div class="flex items-center gap-1.5 mt-0.5">
                        <span class="text-[11px] text-slate-400">#${tx.id}</span>
                        <span class="px-1.5 py-0.2 rounded text-[9px] font-sans font-bold uppercase ${
                          isPenyesuaian ? "bg-purple-50 text-purple-700" : "bg-blue-50 text-blue-700"
                        }">${esc(isPenyesuaian ? "Penyesuaian" : tx.tab_type)}</span>
                      </div>
                    </td>
                    <td class="py-3.5 px-3 max-w-[340px] align-top">
                      <p class="text-slate-900 font-semibold leading-snug">${esc(tx.keterangan)}</p>
                      <p class="text-[11px] text-slate-500 mt-0.5">${esc(tx.kategori)}${
                        tx.tipe === "PINDAH_BUKU" ? ` · ${esc(tx.rekening_sumber)} → ${esc(tx.rekening_tujuan || "-")}` : ""
                      }</p>
                      ${
                        tx.matches?.length
                          ? `<p class="text-[10px] font-semibold text-emerald-700 mt-1">Cocok dgn ${tx.matches.map((m) => `#M${m.mutasi_bank_id} (${esc(m.mutasi_rekening)})`).join(", ")}</p>`
                          : ""
                      }
                    </td>
                    <td class="py-3.5 px-3 text-right font-mono text-sm font-extrabold tabular-nums whitespace-nowrap align-top ${
                      isDebet ? "text-emerald-700" : "text-slate-900"
                    }">
                      ${isDebet ? "+" : "-"}${formatRp(amount)}
                    </td>
                    <td class="py-3.5 px-3 whitespace-nowrap align-top">
                      ${
                        tx.files?.length
                          ? `<button type="button" data-open-gallery="${tx.id}" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-xs font-semibold text-slate-700 transition">${ICON_PHOTO}<span>${tx.files.length}</span></button>`
                          : `<span class="text-[11px] text-slate-400">${isPenyesuaian ? "Mutasi" : "-"}</span>`
                      }
                    </td>
                    <td class="py-3.5 px-3 whitespace-nowrap align-top">
                      <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                    </td>
                    <td class="py-3.5 pl-3 pr-5 text-right whitespace-nowrap align-top">
                      <div class="inline-flex items-center gap-1.5">
                        ${
                          !isMatched
                            ? `<button type="button" data-match-tx="${tx.id}" class="h-8 px-2.5 rounded-lg border border-blue-200 bg-blue-50/70 hover:bg-blue-100 text-blue-700 text-[11px] font-semibold inline-flex items-center gap-1 transition">
                                ${ICON_LINK}<span>Cocokkan</span>
                              </button>`
                            : firstMatch?.match_group_id
                              ? `<button type="button" data-unmatch-group="${esc(firstMatch.match_group_id)}" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold transition">
                                  Lepas
                                </button>`
                              : ""
                        }
                        ${
                          isPenyesuaian
                            ? `<button type="button" data-delete-penyesuaian="${tx.id}" aria-label="Hapus penyesuaian" class="h-8 w-8 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-600 inline-flex items-center justify-center transition">
                                ${ICON_TRASH}
                              </button>`
                            : ""
                        }
                      </div>
                    </td>
                  </tr>
                `;
              })
              .join("")}
          </tbody>
        </table>
      </div>

      <!-- Mobile Cards -->
      <div class="md:hidden divide-y divide-slate-100">
        ${items
          .map((tx) => {
            const badge = TX_STATUS_BADGE[tx.status_rekonsiliasi] || TX_STATUS_BADGE.BELUM_REKON;
            const isMatched = MATCHED_TX_STATUSES.has(tx.status_rekonsiliasi);
            const firstMatch = (tx.matches || [])[0];
            const isPenyesuaian = tx.sumber_pencatatan === "PENYESUAIAN_MUTASI";
            const isDebet = tx.debet > 0;
            const amount = isDebet ? tx.debet : tx.kredit;
            return `
              <article class="p-4 space-y-2.5">
                <div class="flex items-start justify-between gap-2">
                  <div class="min-w-0">
                    <div class="flex flex-wrap items-center gap-1.5">
                      <span class="font-mono text-[11px] text-slate-400">#${tx.id}</span>
                      <span class="font-mono text-[11px] font-semibold text-slate-600">${esc(tx.tanggal_transaksi)}</span>
                      <span class="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-bold uppercase">${esc(isPenyesuaian ? "Penyesuaian" : tx.tab_type)}</span>
                    </div>
                    <p class="text-xs font-bold text-slate-900 mt-1">${esc(tx.keterangan)}</p>
                    <p class="text-[11px] text-slate-500">${esc(tx.kategori)}</p>
                  </div>
                  <span class="font-mono text-sm font-extrabold tabular-nums shrink-0 ${isDebet ? "text-emerald-700" : "text-slate-900"}">${isDebet ? "+" : "-"}${formatRp(amount)}</span>
                </div>
                <div class="flex items-center justify-between gap-2 pt-1">
                  <div class="flex items-center gap-1.5">
                    <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                    ${
                      tx.files?.length
                        ? `<button type="button" data-open-gallery="${tx.id}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border border-slate-200 text-[11px] font-semibold text-slate-700">${ICON_PHOTO}<span>${tx.files.length}</span></button>`
                        : ""
                    }
                  </div>
                  <div class="flex items-center gap-1.5">
                    ${
                      !isMatched
                        ? `<button type="button" data-match-tx="${tx.id}" class="h-8 px-2.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 text-[11px] font-semibold">Cocokkan</button>`
                        : firstMatch?.match_group_id
                          ? `<button type="button" data-unmatch-group="${esc(firstMatch.match_group_id)}" class="h-8 px-2.5 rounded-lg border border-slate-200 text-slate-700 text-[11px] font-semibold">Lepas</button>`
                          : ""
                    }
                    ${
                      isPenyesuaian
                        ? `<button type="button" data-delete-penyesuaian="${tx.id}" class="h-8 w-8 rounded-lg border border-rose-200 text-rose-600 inline-flex items-center justify-center">${ICON_TRASH}</button>`
                        : ""
                    }
                  </div>
                </div>
              </article>
            `;
          })
          .join("")}
      </div>
    `;
  }

  function renderReconcileCard(report) {
    const mutAll = report.mutasi_rows || [];
    const mutUnmatched = mutAll.filter((m) => UNMATCHED_MUTASI_STATUSES.has(m.status_rekonsiliasi)).length;
    const txAll = report.rows || [];
    const txUnmatched = txAll.filter((t) => !MATCHED_TX_STATUSES.has(t.status_rekonsiliasi)).length;

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
        <div class="p-4 sm:p-5 border-b border-slate-100 space-y-3.5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <!-- Sub-tab Mutasi Bank vs Catatan Struk -->
            <div class="inline-flex p-1 rounded-2xl bg-slate-100 self-start">
              <button type="button" data-recon-subtab="mutasi" class="h-8 px-3.5 rounded-xl text-xs font-semibold transition inline-flex items-center gap-1.5 ${
                state.reconSubTab === "mutasi" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }">
                <span>Mutasi Bank</span>
                <span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
                  mutUnmatched > 0 ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-700"
                }">${mutAll.length}</span>
              </button>
              <button type="button" data-recon-subtab="struk" class="h-8 px-3.5 rounded-xl text-xs font-semibold transition inline-flex items-center gap-1.5 ${
                state.reconSubTab === "struk" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
              }">
                <span>Catatan Struk</span>
                <span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
                  txUnmatched > 0 ? "bg-amber-100 text-amber-800" : "bg-slate-200 text-slate-700"
                }">${txAll.length}</span>
              </button>
            </div>

            <!-- Filter Pills (Gaya Input Struk & Input Mutasi) -->
            <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar">
              ${[
                { id: "all", label: "Semua" },
                { id: "unmatched", label: "Belum Cocok" },
                { id: "matched", label: "Sudah Cocok" },
              ]
                .map((f) => {
                  const active = state.reconFilter === f.id;
                  return `<button type="button" data-recon-filter="${f.id}" class="shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold transition ${
                    active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200/70"
                  }">${esc(f.label)}</button>`;
                })
                .join("")}
            </div>
          </div>

          <div class="relative">
            <span class="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input
              type="text"
              data-recon-search
              value="${esc(state.reconSearch)}"
              placeholder="${state.reconSubTab === "mutasi" ? "Cari uraian mutasi, nominal, tanggal, atau #M..." : "Cari keterangan, kategori, nominal, atau #ID..."}"
              class="w-full h-10 pl-10 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
            />
          </div>
        </div>

        <div data-recon-list>${renderReconcileBody(report)}</div>
      </div>
    `;
  }

  function renderCashReportBody(report) {
    const q = state.reportSearch.trim().toLowerCase();
    const rows = q
      ? (report.rows || []).filter((r) =>
          `${r.id} ${r.tanggal_transaksi} ${r.keterangan} ${r.kategori} ${r.uang_masuk} ${r.uang_keluar}`.toLowerCase().includes(q)
        )
      : report.rows || [];

    const saldoAwalRow = `
      <tr class="bg-slate-50/80">
        <td class="py-3 pl-5 pr-3 text-slate-400">-</td>
        <td class="py-3 px-3 font-mono whitespace-nowrap">${esc(formatTanggalId(report.start_date))}</td>
        <td class="py-3 px-3 font-bold text-slate-900">Saldo Awal</td>
        <td class="py-3 px-3">Saldo Awal</td>
        <td class="py-3 px-3 text-slate-400">-</td>
        <td class="py-3 px-3 text-slate-400">-</td>
        <td class="py-3 px-3 text-right font-mono font-semibold">${formatRp(report.saldo_awal)}</td>
        <td class="py-3 px-3 text-right font-mono text-slate-400">-</td>
        <td class="py-3 px-3 text-right font-mono font-bold">${formatRp(report.saldo_awal)}</td>
        <td class="py-3 px-3 text-slate-400">-</td>
        <td class="py-3 pl-3 pr-5"></td>
      </tr>`;

    const bodyRows = rows
      .map((row) => {
        const badge = TX_STATUS_BADGE[row.status_rekonsiliasi] || TX_STATUS_BADGE.BELUM_REKON;
        const lampiranCell = row.files?.length
          ? `<button type="button" data-open-gallery="${row.id}" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold whitespace-nowrap transition">${ICON_PHOTO}<span>${row.files.length}</span></button>`
          : `<span class="text-slate-500 text-[11px] whitespace-nowrap">${esc(row.lampiran)}</span>`;
        return `
          <tr class="hover:bg-slate-50/70 align-top transition">
            <td class="py-3 pl-5 pr-3 text-slate-500 text-[11px]">${esc(row.tanggal_input_admin)}</td>
            <td class="py-3 px-3 font-mono whitespace-nowrap">${esc(formatTanggalId(row.tanggal_transaksi))}</td>
            <td class="py-3 px-3 text-slate-900 font-medium max-w-[300px]">${esc(row.keterangan)}</td>
            <td class="py-3 px-3 text-slate-700">${esc(row.kategori)}</td>
            <td class="py-3 px-3">${row.uang_masuk ? esc(row.uang_masuk) : '<span class="text-slate-400">-</span>'}</td>
            <td class="py-3 px-3">${row.uang_keluar ? esc(row.uang_keluar) : '<span class="text-slate-400">-</span>'}</td>
            <td class="py-3 px-3 text-right font-mono font-semibold text-emerald-700 whitespace-nowrap">${row.debet ? formatRp(row.debet) : "-"}</td>
            <td class="py-3 px-3 text-right font-mono font-semibold text-rose-700 whitespace-nowrap">${row.kredit ? formatRp(row.kredit) : "-"}</td>
            <td class="py-3 px-3 text-right font-mono font-bold text-slate-900 whitespace-nowrap">${formatRp(row.saldo)}</td>
            <td class="py-3 px-3">${lampiranCell}</td>
            <td class="py-3 pl-3 pr-5 whitespace-nowrap"><span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span></td>
          </tr>`;
      })
      .join("");

    const emptyRow = rows.length
      ? ""
      : `<tr><td colspan="11" class="py-10 px-4 text-center text-xs text-slate-500">Belum ada transaksi untuk ${esc(report.rekening.kode_akun)} pada ${esc(report.month_label)}.</td></tr>`;

    const footer = `
      <tr class="bg-slate-50 font-bold border-t-2 border-slate-200">
        <td></td><td colspan="5" class="py-3 px-3">SUB TOTAL (Debet termasuk Saldo Awal)</td>
        <td class="py-3 px-3 text-right font-mono">${formatRp(report.sub_total_debet)}</td>
        <td class="py-3 px-3 text-right font-mono">${formatRp(report.total_kredit)}</td>
        <td colspan="3"></td>
      </tr>
      <tr class="bg-slate-50 font-bold">
        <td></td><td colspan="5" class="py-2.5 px-3">SISA SALDO</td>
        <td></td>
        <td class="py-2.5 px-3 text-right font-mono">${formatRp(report.sisa_saldo)}</td>
        <td colspan="3"></td>
      </tr>
      <tr class="bg-slate-50 font-bold">
        <td></td><td colspan="5" class="py-3 px-3">GRAND TOTAL</td>
        <td class="py-3 px-3 text-right font-mono">${formatRp(report.sub_total_debet)}</td>
        <td class="py-3 px-3 text-right font-mono">${formatRp(round2(report.total_kredit + report.sisa_saldo))}</td>
        <td colspan="3"></td>
      </tr>`;

    return `
      <!-- Desktop Table -->
      <div class="hidden md:block overflow-x-auto max-h-[560px]">
        <table class="w-full text-left border-collapse text-xs min-w-[1020px]">
          <thead class="sticky top-0 z-10 bg-slate-50/95 backdrop-blur-xs border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th class="py-3 pl-5 pr-3">Tgl Input / Admin</th>
              <th class="py-3 px-3">Tgl Transaksi</th>
              <th class="py-3 px-3">Keterangan</th>
              <th class="py-3 px-3">Kategori</th>
              <th class="py-3 px-3">Uang Masuk</th>
              <th class="py-3 px-3">Uang Keluar</th>
              <th class="py-3 px-3 text-right">Debet</th>
              <th class="py-3 px-3 text-right">Kredit</th>
              <th class="py-3 px-3 text-right">Saldo</th>
              <th class="py-3 px-3">Lampiran</th>
              <th class="py-3 pl-3 pr-5">Status Rekon</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-100">${saldoAwalRow + bodyRows + emptyRow + footer}</tbody>
        </table>
      </div>

      <!-- Mobile Cards -->
      <div class="md:hidden divide-y divide-slate-100">
        <article class="p-4 bg-slate-50/80 flex items-center justify-between gap-2">
          <div>
            <p class="text-xs font-bold text-slate-900">Saldo Awal</p>
            <p class="font-mono text-[11px] text-slate-500">${esc(formatTanggalId(report.start_date))}</p>
          </div>
          <span class="font-mono text-sm font-extrabold text-slate-900">${formatRp(report.saldo_awal)}</span>
        </article>
        ${
          rows.length
            ? rows
                .map((row) => {
                  const badge = TX_STATUS_BADGE[row.status_rekonsiliasi] || TX_STATUS_BADGE.BELUM_REKON;
                  const isDebet = row.debet > 0;
                  return `
                    <article class="p-4 space-y-2">
                      <div class="flex items-start justify-between gap-2">
                        <div class="min-w-0">
                          <span class="font-mono text-[11px] text-slate-500">${esc(formatTanggalId(row.tanggal_transaksi))}</span>
                          <p class="text-xs font-bold text-slate-900 mt-0.5">${esc(row.keterangan)}</p>
                          <p class="text-[11px] text-slate-500">${esc(row.kategori)}</p>
                        </div>
                        <div class="text-right shrink-0">
                          <p class="font-mono text-sm font-extrabold ${isDebet ? "text-emerald-700" : "text-rose-700"}">${isDebet ? "+" : "-"}${formatRp(isDebet ? row.debet : row.kredit)}</p>
                          <p class="font-mono text-[10px] text-slate-500">Saldo ${formatRp(row.saldo)}</p>
                        </div>
                      </div>
                      <div class="flex items-center justify-between gap-2 pt-1">
                        <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                        ${
                          row.files?.length
                            ? `<button type="button" data-open-gallery="${row.id}" class="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 text-[11px] font-semibold text-slate-700">${ICON_PHOTO}<span>Lampiran (${row.files.length})</span></button>`
                            : `<span class="text-[11px] text-slate-400">${esc(row.lampiran)}</span>`
                        }
                      </div>
                    </article>
                  `;
                })
                .join("")
            : `<div class="p-8 text-center text-xs text-slate-500">Belum ada transaksi bulan ini.</div>`
        }
        <div class="p-4 bg-slate-50 space-y-1.5 text-xs font-bold">
          <div class="flex justify-between"><span>SUB TOTAL (Debet / Kredit)</span><span class="font-mono">${formatRp(report.sub_total_debet)} / ${formatRp(report.total_kredit)}</span></div>
          <div class="flex justify-between"><span>SISA SALDO</span><span class="font-mono">${formatRp(report.sisa_saldo)}</span></div>
        </div>
      </div>
    `;
  }

  function renderCashReportCard(report) {
    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
        <div class="p-4 sm:p-5 border-b border-slate-100 space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 class="text-sm font-bold text-slate-900">${esc(report.title)} — ${esc(report.month_label)}</h3>
              <p class="text-[11px] text-slate-500">${esc(report.company)}${report.subtitle ? ` · ${esc(report.subtitle)}` : ""}</p>
            </div>
            <span class="px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700">${report.rows.length} transaksi</span>
          </div>
          <div class="relative">
            <span class="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input
              type="text"
              data-report-search
              value="${esc(state.reportSearch)}"
              placeholder="Filter baris Cash Report berdasarkan keterangan, kategori, atau rekening..."
              class="w-full h-10 pl-10 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
            />
          </div>
        </div>
        <div data-report-list>${renderCashReportBody(report)}</div>
      </div>
    `;
  }

  function render() {
    const report = computeEffectiveReport();
    const isCash = Boolean(selectedRekening()?.is_cash);
    const activeView = isCash ? "cash_report" : state.view;

    const wrapper = document.createElement("div");
    wrapper.className = "space-y-5 view-animate";
    if (state.loadingMeta && !state.rekening.length) {
      wrapper.innerHTML = `${renderTopBar(null)}<div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center text-xs text-slate-500">Memuat data rekonsiliasi…</div>`;
      container.replaceChildren(wrapper);
      bindEvents(wrapper);
      return;
    }

    let bodyHtml = "";
    if (state.loadingMeta || state.loadingReport) {
      bodyHtml = `<div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center text-xs text-slate-500">Memuat data rekonsiliasi…</div>`;
    } else if (!report) {
      bodyHtml = `<div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center text-xs text-slate-500">Belum ada data laporan untuk pilihan ini.</div>`;
    } else if (activeView === "reconcile") {
      bodyHtml = renderReconcileCard(report);
    } else {
      bodyHtml = renderCashReportCard(report);
    }

    wrapper.innerHTML = `${renderTopBar(report)}${renderControlCard(report)}${bodyHtml}`;
    container.replaceChildren(wrapper);
    bindEvents(wrapper);
  }

  /* ------------------------- Data Loaders ------------------------- */

  async function loadReport() {
    const rekening = selectedRekening();
    if (!rekening || !state.monthKey) {
      state.report = null;
      render();
      return;
    }

    const reqId = ++state.reportRequestId;
    state.loadingReport = true;
    render();

    try {
      const params = new URLSearchParams({
        rekening_id: String(rekening.id),
        month: String(state.monthKey),
      });
      const data = await apiJson(`/rekonsiliasi/report?${params.toString()}`, {}, onUnauthorized);
      if (reqId !== state.reportRequestId) return;
      state.report = data;
    } catch (err) {
      if (reqId !== state.reportRequestId) return;
      state.report = null;
      state.error = err.message || "Gagal memuat laporan rekonsiliasi.";
    } finally {
      if (reqId === state.reportRequestId) {
        state.loadingReport = false;
        render();
      }
    }
  }

  async function loadAll() {
    const reqId = ++state.metaRequestId;
    state.loadingMeta = true;
    state.error = "";
    render();

    try {
      const meta = await apiJson("/rekonsiliasi/metadata", {}, onUnauthorized);
      if (reqId !== state.metaRequestId) return;

      state.rekening = meta.rekening_perusahaan || [];
      state.kategori = meta.kategori_sop || [];
      state.months = meta.months || [];
      state.activity = meta.activity_by_rekening || {};

      if (!state.rekening.some((r) => String(r.id) === String(state.rekeningId))) {
        state.rekeningId = defaultRekeningId();
      }
      if (!state.monthKey || !state.months.includes(state.monthKey)) {
        state.monthKey = defaultMonthFor(state.rekeningId);
      }
    } catch (err) {
      if (reqId !== state.metaRequestId) return;
      state.error = err.message || "Gagal memuat metadata rekonsiliasi.";
      state.loadingMeta = false;
      render();
      return;
    }

    state.loadingMeta = false;
    await loadReport();
  }

  /* ------------------------- Modals ------------------------- */

  function createModalShell({ title, subtitle, maxWidth = "max-w-xl", onClose = null }) {
    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 bg-slate-950/55 backdrop-blur-xs flex items-end sm:items-center justify-center p-0 sm:p-4";
    modal.innerHTML = `
      <div class="modal-panel-animate w-full ${maxWidth} rounded-t-3xl sm:rounded-3xl bg-white border border-slate-200 shadow-2xl overflow-hidden max-h-[90vh] flex flex-col">
        <div class="px-5 py-4 border-b border-slate-100 flex items-start justify-between gap-3 shrink-0">
          <div class="min-w-0">
            <h3 class="text-sm font-bold text-slate-900 truncate">${esc(title)}</h3>
            <p class="text-[11px] text-slate-500 truncate mt-0.5">${esc(subtitle)}</p>
          </div>
          <button type="button" data-close-modal aria-label="Tutup" class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-600 flex items-center justify-center shrink-0 transition">
            ${ICON_CLOSE}
          </button>
        </div>
        <div data-modal-body class="overflow-y-auto"></div>
      </div>
    `;
    const onKey = (e) => {
      if (e.key === "Escape") close();
    };
    const close = () => {
      document.removeEventListener("keydown", onKey);
      if (typeof onClose === "function") onClose();
      modal.remove();
    };
    document.addEventListener("keydown", onKey);
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close-modal]")) close();
    });
    document.body.appendChild(modal);
    return { modal, body: modal.querySelector("[data-modal-body]"), close };
  }

  async function openGalleryModal(tx) {
    const files = tx.files || [];
    if (!files.length) return;
    const blobUrls = new Map();
    const { body } = createModalShell({
      title: `Lampiran Bukti — Transaksi #${tx.id}`,
      subtitle: tx.keterangan,
      maxWidth: "max-w-2xl",
      onClose: () => {
        for (const u of blobUrls.values()) URL.revokeObjectURL(u);
      },
    });

    body.innerHTML = `
      <div class="p-4 sm:p-5 space-y-3">
        <div data-gallery-box class="rounded-2xl bg-slate-100 min-h-[280px] max-h-[60vh] flex items-center justify-center overflow-hidden p-2">
          <span class="text-xs text-slate-500">Memuat gambar…</span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          ${files
            .map(
              (f, idx) =>
                `<button type="button" data-thumb-idx="${idx}" class="px-2.5 py-1.5 rounded-xl text-[11px] font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition">Slot ${esc(f.slot)} · ${esc(f.orig_filename)}</button>`
            )
            .join("")}
        </div>
      </div>
    `;

    const box = body.querySelector("[data-gallery-box]");
    async function showFile(idx) {
      const f = files[idx];
      if (!f || !box) return;
      body.querySelectorAll("[data-thumb-idx]").forEach((btn) => {
        const active = Number(btn.dataset.thumbIdx) === idx;
        btn.className = `px-2.5 py-1.5 rounded-xl text-[11px] font-semibold transition ${
          active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
        }`;
      });
      box.innerHTML = `<span class="text-xs text-slate-500">Memuat gambar…</span>`;
      try {
        let u = blobUrls.get(f.id);
        if (!u) {
          const path = String(f.url).replace(/^\/api\/v1/, "");
          const res = await apiFetch(path, {}, onUnauthorized);
          if (!res.ok) throw new Error("Gagal memuat file bukti");
          u = URL.createObjectURL(await res.blob());
          blobUrls.set(f.id, u);
        }
        box.innerHTML = `<img src="${u}" alt="${esc(f.orig_filename)}" class="max-h-[56vh] w-full object-contain rounded-xl" />`;
      } catch (err) {
        box.innerHTML = `<p class="text-xs font-semibold text-rose-600">${esc(err.message)}</p>`;
      }
    }

    body.querySelectorAll("[data-thumb-idx]").forEach((btn) => {
      btn.addEventListener("click", () => showFile(Number(btn.dataset.thumbIdx)));
    });
    showFile(0);
  }

  function openMatchFromMutasiModal(mutasi) {
    const report = state.report;
    if (!report) return;

    const allCandidates = report.rows
      .filter((tx) => {
        if (MATCHED_TX_STATUSES.has(tx.status_rekonsiliasi)) return false;
        if (tx.tipe === "MASUK") return mutasi.tipe === "CR" && tx.rekening_sumber_id === mutasi.rekening_id;
        if (tx.tipe === "KELUAR") return mutasi.tipe === "DB" && tx.rekening_sumber_id === mutasi.rekening_id;
        return (
          (mutasi.tipe === "DB" && tx.rekening_sumber_id === mutasi.rekening_id) ||
          (mutasi.tipe === "CR" && tx.rekening_tujuan_id === mutasi.rekening_id)
        );
      })
      .map((tx) => {
        const amount = tx.debet > 0 ? tx.debet : tx.kredit;
        const diff = round2(Number(mutasi.nominal) - Number(amount));
        const dist = dateDistanceDays(tx.tanggal_transaksi, mutasi.tanggal);
        return { tx, amount, diff, dist, recommended: Math.abs(diff) <= 1000 && dist <= 3 };
      })
      .sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0) || a.dist - b.dist || Math.abs(a.diff) - Math.abs(b.diff));

    const { body, close } = createModalShell({
      title: `Cocokkan Mutasi #M${mutasi.id}`,
      subtitle: `${formatTanggalId(mutasi.tanggal)} · ${mutasi.tipe} ${formatRp(mutasi.nominal)}`,
    });

    body.innerHTML = `
      <form data-match-form class="p-5 space-y-4">
        <div class="rounded-2xl bg-slate-50 border border-slate-200/80 p-3 text-xs text-slate-700">${esc(mutasi.uraian)}</div>

        <div class="space-y-2">
          <div class="flex items-center justify-between gap-2">
            <label class="text-xs font-semibold text-slate-700">Pilih Transaksi Input Struk (${allCandidates.length})</label>
          </div>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input type="text" data-cand-search placeholder="Cari keterangan atau nominal…" class="w-full h-9 pl-9 pr-3 rounded-xl bg-slate-50 border border-slate-200 text-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20" />
          </div>
          <div data-cand-list class="max-h-56 overflow-y-auto divide-y divide-slate-100 rounded-2xl border border-slate-200"></div>
        </div>

        <label class="block space-y-1">
          <span class="text-xs font-semibold text-slate-700">Catatan Rekonsiliasi (opsional)</span>
          <input type="text" name="catatan" placeholder="Mis. beda tanggal kliring atau selisih kode unik" class="${INPUT_CLS}" />
        </label>

        <p data-modal-err class="hidden rounded-xl bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"></p>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button type="button" data-close-modal class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50">Batal</button>
          <button type="submit" ${allCandidates.length ? "" : "disabled"} class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold disabled:opacity-40">Simpan Kecocokan</button>
        </div>
      </form>
    `;

    const listEl = body.querySelector("[data-cand-list]");
    const searchEl = body.querySelector("[data-cand-search]");
    const renderCandidates = (q = "") => {
      const term = q.trim().toLowerCase();
      const filtered = term
        ? allCandidates.filter((c) => `${c.tx.id} ${c.tx.keterangan} ${c.amount}`.toLowerCase().includes(term))
        : allCandidates;
      if (!filtered.length) {
        listEl.innerHTML = `<p class="p-4 text-center text-xs text-slate-500">Tidak ada kandidat Struk yang cocok. Gunakan "Penyesuaian" bila belum ada struk.</p>`;
        return;
      }
      listEl.innerHTML = filtered
        .map(
          ({ tx, amount, diff, recommended }, idx) => `
            <label class="flex items-start gap-2.5 p-3 hover:bg-slate-50 cursor-pointer text-xs">
              <input type="radio" name="transaksi_id" value="${tx.id}" ${idx === 0 ? "checked" : ""} class="mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-semibold text-slate-900">#${esc(tx.id)} · ${esc(formatTanggalId(tx.tanggal_transaksi))}</span>
                  <span class="font-mono font-bold text-slate-900">${formatRp(amount)}</span>
                </div>
                <p class="text-[11px] text-slate-600 truncate">${esc(tx.keterangan)}</p>
                <div class="flex items-center gap-2 mt-0.5">
                  <span class="text-[10px] text-slate-400">Selisih: ${formatRp(diff)}</span>
                  ${recommended ? `<span class="px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 text-[9px] font-bold">Saran Cocok</span>` : ""}
                </div>
              </div>
            </label>
          `
        )
        .join("");
    };
    renderCandidates();
    searchEl.addEventListener("input", (e) => renderCandidates(e.target.value));

    const form = body.querySelector("[data-match-form]");
    const errEl = body.querySelector("[data-modal-err]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const txId = Number(form.elements["transaksi_id"]?.value);
      if (!txId) return;
      errEl.classList.add("hidden");
      try {
        await apiJson(
          "/rekonsiliasi/match",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              transaksi_id: txId,
              mutasi_ids: [mutasi.id],
              catatan: String(form.elements["catatan"]?.value || ""),
            }),
          },
          onUnauthorized
        );
        close();
        state.notice = `Mutasi #M${mutasi.id} berhasil dicocokkan dengan Transaksi #${txId}.`;
        await loadAll();
      } catch (err) {
        errEl.textContent = err.message || "Gagal menyimpan kecocokan.";
        errEl.classList.remove("hidden");
      }
    });
  }

  function openMatchFromTxModal(tx) {
    const report = state.report;
    if (!report) return;

    const targetAmount = tx.debet > 0 ? tx.debet : tx.kredit;
    const expectedMutTipe = tx.debet > 0 ? "CR" : "DB";
    const candidates = (report.mutasi_rows || [])
      .filter((m) => UNMATCHED_MUTASI_STATUSES.has(m.status_rekonsiliasi) && m.tipe === expectedMutTipe)
      .map((m) => {
        const diff = Math.abs(Number(m.nominal) - Number(targetAmount));
        const dist = dateDistanceDays(m.tanggal, tx.tanggal_transaksi);
        return { m, diff, dist, recommended: diff <= 1000 && dist <= 3 };
      })
      .sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0) || a.dist - b.dist || a.diff - b.diff);

    const { body, close } = createModalShell({
      title: `Cocokkan Transaksi #${tx.id}`,
      subtitle: `${formatTanggalId(tx.tanggal_transaksi)} · ${formatRp(targetAmount)} (${expectedMutTipe})`,
    });

    body.innerHTML = `
      <form data-match-tx-form class="p-5 space-y-4">
        <div class="rounded-2xl bg-slate-50 border border-slate-200/80 p-3 text-xs text-slate-700">${esc(tx.keterangan)}</div>

        <div class="space-y-2">
          <div class="flex items-center justify-between gap-2">
            <label class="text-xs font-semibold text-slate-700">Pilih 1+ baris Mutasi (${esc(expectedMutTipe)})</label>
            <span data-split-summary class="text-[11px] font-mono font-bold text-slate-700">Dipilih: Rp0</span>
          </div>
          <div class="relative">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input type="text" data-mut-cand-search placeholder="Cari uraian mutasi atau nominal…" class="w-full h-9 pl-9 pr-3 rounded-xl bg-slate-50 border border-slate-200 text-xs focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20" />
          </div>
          <div data-mut-cand-list class="max-h-56 overflow-y-auto divide-y divide-slate-100 rounded-2xl border border-slate-200"></div>
        </div>

        <label class="block space-y-1">
          <span class="text-xs font-semibold text-slate-700">Catatan Rekonsiliasi (opsional)</span>
          <input type="text" name="catatan" placeholder="Mis. split biaya admin bank atau beda hari kliring" class="${INPUT_CLS}" />
        </label>

        <p data-modal-err class="hidden rounded-xl bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"></p>

        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button type="button" data-close-modal class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50">Batal</button>
          <button type="submit" ${candidates.length ? "" : "disabled"} class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold disabled:opacity-40">Simpan Kecocokan</button>
        </div>
      </form>
    `;

    const listEl = body.querySelector("[data-mut-cand-list]");
    const searchEl = body.querySelector("[data-mut-cand-search]");
    const splitSummary = body.querySelector("[data-split-summary]");
    const selectedIds = new Set();

    const updateSum = () => {
      const totalSel = round2(
        candidates
          .filter(({ m }) => selectedIds.has(Number(m.id)))
          .reduce((s, { m }) => s + Number(m.nominal || 0), 0)
      );
      const diff = round2(totalSel - Number(targetAmount));
      splitSummary.textContent = `Dipilih: ${formatRp(totalSel)} (selisih ${formatRp(diff)})`;
    };

    const renderList = (q = "") => {
      const term = q.trim().toLowerCase();
      const filtered = term
        ? candidates.filter(({ m }) => `${m.id} ${m.uraian} ${m.nominal} ${m.tanggal}`.toLowerCase().includes(term))
        : candidates;
      if (!filtered.length) {
        listEl.innerHTML = `<p class="p-4 text-center text-xs text-slate-500">Tidak ada baris mutasi ${esc(expectedMutTipe)} yang belum cocok.</p>`;
        return;
      }
      listEl.innerHTML = filtered
        .map(
          ({ m, recommended }) => `
            <label class="flex items-start gap-2.5 p-3 hover:bg-slate-50 cursor-pointer text-xs">
              <input type="checkbox" name="mutasi_id" value="${m.id}" ${selectedIds.has(Number(m.id)) ? "checked" : ""} class="mt-0.5" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center justify-between gap-2">
                  <span class="font-semibold text-slate-900">#M${esc(m.id)} · ${esc(formatTanggalId(m.tanggal))}</span>
                  <span class="font-mono font-bold text-slate-900">${formatRp(m.nominal)}</span>
                </div>
                <p class="text-[11px] text-slate-600 break-words">${esc(m.uraian)}</p>
                ${recommended ? `<span class="inline-block mt-0.5 px-1.5 py-0.2 rounded bg-emerald-50 text-emerald-700 text-[9px] font-bold">Saran Cocok</span>` : ""}
              </div>
            </label>
          `
        )
        .join("");

      listEl.querySelectorAll('input[name="mutasi_id"]').forEach((cb) => {
        cb.addEventListener("change", () => {
          const mid = Number(cb.value);
          if (cb.checked) selectedIds.add(mid);
          else selectedIds.delete(mid);
          updateSum();
        });
      });
    };

    renderList();
    searchEl.addEventListener("input", (e) => renderList(e.target.value));

    const form = body.querySelector("[data-match-tx-form]");
    const errEl = body.querySelector("[data-modal-err]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const ids = [...selectedIds];
      if (!ids.length) {
        errEl.textContent = "Pilih minimal satu baris mutasi.";
        errEl.classList.remove("hidden");
        return;
      }
      errEl.classList.add("hidden");
      try {
        await apiJson(
          "/rekonsiliasi/match",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              transaksi_id: tx.id,
              mutasi_ids: ids,
              catatan: String(form.elements["catatan"]?.value || ""),
            }),
          },
          onUnauthorized
        );
        close();
        state.notice = `Transaksi #${tx.id} berhasil dicocokkan dengan ${ids.length} baris mutasi.`;
        await loadAll();
      } catch (err) {
        errEl.textContent = err.message || "Gagal menyimpan kecocokan.";
        errEl.classList.remove("hidden");
      }
    });
  }

  function openPenyesuaianModal(mutasi) {
    const isCr = mutasi.tipe === "CR";
    const defaultTipe = isCr ? "MASUK" : "KELUAR";
    const upperUraian = String(mutasi.uraian || "").toUpperCase();
    const isBankFeeOrInterest = /INTEREST|BUNGA|TAX|PAJAK|ADMIN|BIAYA|MATERAI/.test(upperUraian);

    const defaultCat =
      state.kategori.find((c) => {
        if (isBankFeeOrInterest) {
          return isCr
            ? /pendapatan\/beban lain/i.test(c.nama_kategori)
            : /administrasi|operasional|pendapatan\/beban lain/i.test(c.nama_kategori);
        }
        return isCr ? c.kelompok === "PEMASUKAN" : c.kelompok === "PENGELUARAN";
      }) || state.kategori[0];

    const otherAccounts = state.rekening.filter((r) => Number(r.id) !== Number(mutasi.rekening_id));
    const pindahCat = state.kategori.find((c) => /pindah buku/i.test(c.nama_kategori));

    const { body, close } = createModalShell({
      title: `Catat Penyesuaian Mutasi #M${mutasi.id}`,
      subtitle: `${formatTanggalId(mutasi.tanggal)} · ${mutasi.tipe} ${formatRp(mutasi.nominal)}`,
      maxWidth: "max-w-lg",
    });

    body.innerHTML = `
      <form data-adj-form class="p-5 space-y-3.5">
        <div class="rounded-2xl bg-slate-50 border border-slate-200/80 p-3 text-xs text-slate-700">${esc(mutasi.uraian)}</div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="block text-xs font-semibold text-slate-700">Tipe Transaksi</span>
            <select name="tipe" data-adj-tipe class="${INPUT_CLS}">
              <option value="${defaultTipe}" selected>${defaultTipe}</option>
              <option value="PINDAH_BUKU">PINDAH_BUKU</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="block text-xs font-semibold text-slate-700">Kategori SOP</span>
            <select name="kategori_id" required class="${INPUT_CLS}">
              ${state.kategori
                .map(
                  (c) =>
                    `<option value="${c.id}" ${defaultCat && c.id === defaultCat.id ? "selected" : ""}>${c.no_urut}. ${esc(c.nama_kategori)}</option>`
                )
                .join("")}
            </select>
          </label>
        </div>

        <label data-adj-counterpart-wrap class="hidden space-y-1">
          <span class="block text-xs font-semibold text-slate-700">${isCr ? "Dari Rekening Sumber" : "Ke Rekening Tujuan"}</span>
          <select name="counterpart_id" class="${INPUT_CLS}">
            <option value="">-- Pilih Rekening --</option>
            ${otherAccounts.map((a) => `<option value="${a.id}">${esc(a.kode_akun)} — ${esc(a.bank_lembaga)}</option>`).join("")}
          </select>
        </label>

        <label class="block space-y-1">
          <span class="block text-xs font-semibold text-slate-700">Penerima / Pengirim (opsional)</span>
          <input type="text" name="penerima_pengirim" placeholder="Mis. Bank BNI / Nama Pihak" class="${INPUT_CLS}" />
        </label>

        <label class="block space-y-1">
          <span class="block text-xs font-semibold text-slate-700">Keterangan Cash Report</span>
          <input type="text" name="keterangan" value="${esc(mutasi.uraian)}" required class="${INPUT_CLS}" />
        </label>

        <label class="block space-y-1">
          <span class="block text-xs font-semibold text-slate-700">Catatan Penyesuaian (opsional)</span>
          <input type="text" name="catatan" value="${esc(mutasi.penyebab_selisih || "Penyesuaian mutasi bank")}" class="${INPUT_CLS}" />
        </label>

        <p data-modal-err class="hidden rounded-xl bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"></p>
        <div class="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button type="button" data-close-modal class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50">Batal</button>
          <button type="submit" class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold">Simpan Penyesuaian</button>
        </div>
      </form>
    `;

    const form = body.querySelector("[data-adj-form]");
    const tipeEl = form.querySelector("[data-adj-tipe]");
    const counterpartWrap = form.querySelector("[data-adj-counterpart-wrap]");
    const errEl = body.querySelector("[data-modal-err]");

    tipeEl.addEventListener("change", () => {
      const isPb = tipeEl.value === "PINDAH_BUKU";
      counterpartWrap.classList.toggle("hidden", !isPb);
      if (isPb && pindahCat) form.elements["kategori_id"].value = String(pindahCat.id);
    });

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const tipe = form.elements["tipe"].value;
      const counterpartId = form.elements["counterpart_id"].value ? Number(form.elements["counterpart_id"].value) : null;
      if (tipe === "PINDAH_BUKU" && !counterpartId) {
        errEl.textContent = "Pilih rekening lawan untuk Pindah Buku.";
        errEl.classList.remove("hidden");
        return;
      }

      errEl.classList.add("hidden");
      try {
        await apiJson(
          "/rekonsiliasi/penyesuaian",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              mutasi_id: mutasi.id,
              kategori_id: Number(form.elements["kategori_id"].value),
              tipe,
              rekening_sumber_id: tipe === "PINDAH_BUKU" && isCr ? counterpartId : null,
              rekening_tujuan_id: tipe === "PINDAH_BUKU" && !isCr ? counterpartId : null,
              penerima_pengirim: String(form.elements["penerima_pengirim"].value || ""),
              keterangan: String(form.elements["keterangan"].value || ""),
              catatan: String(form.elements["catatan"].value || ""),
            }),
          },
          onUnauthorized
        );
        close();
        state.notice = `Mutasi #M${mutasi.id} dicatat sebagai Penyesuaian Mutasi.`;
        await loadAll();
      } catch (err) {
        errEl.textContent = err.message || "Gagal menyimpan penyesuaian mutasi.";
        errEl.classList.remove("hidden");
      }
    });
  }

  /* ------------------------- Events ------------------------- */

  function bindEvents(root) {
    root.querySelectorAll("[data-switch-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.view = btn.dataset.switchView;
        render();
      });
    });

    root.querySelectorAll("[data-select-rekening]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const nextId = Number(btn.dataset.selectRekening);
        if (nextId === Number(state.rekeningId)) return;
        state.rekeningId = nextId;
        state.saldoAwalManual = null;
        state.editingSaldo = false;
        state.notice = "";
        state.error = "";
        await loadReport();
      });
    });

    root.querySelector("[data-filter-month]")?.addEventListener("change", async (e) => {
      state.monthKey = e.target.value;
      state.saldoAwalManual = null;
      state.editingSaldo = false;
      state.notice = "";
      state.error = "";
      await loadReport();
    });

    root.querySelectorAll("[data-month-nav]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idx = state.months.indexOf(state.monthKey);
        const nextIdx = btn.dataset.monthNav === "older" ? idx + 1 : idx - 1;
        if (nextIdx < 0 || nextIdx >= state.months.length) return;
        state.monthKey = state.months[nextIdx];
        state.saldoAwalManual = null;
        state.editingSaldo = false;
        state.notice = "";
        state.error = "";
        await loadReport();
      });
    });

    root.querySelector('[data-action="edit-saldo"]')?.addEventListener("click", () => {
      state.editingSaldo = true;
      render();
      const inp = container.querySelector('[data-saldo-form] input[name="saldo_input"]');
      if (inp) {
        inp.focus();
        inp.select();
      }
    });

    root.querySelector("[data-saldo-form]")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const raw = e.target.elements["saldo_input"]?.value.trim();
      if (raw !== "" && Number.isFinite(Number(raw))) {
        state.saldoAwalManual = round2(Number(raw));
      }
      state.editingSaldo = false;
      render();
    });

    root.querySelector('[data-action="cancel-saldo"]')?.addEventListener("click", () => {
      state.editingSaldo = false;
      render();
    });

    root.querySelector('[data-saldo-form] input[name="saldo_input"]')?.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        state.editingSaldo = false;
        render();
      }
    });

    root.querySelector('[data-action="reset-saldo"]')?.addEventListener("click", () => {
      state.saldoAwalManual = null;
      state.editingSaldo = false;
      render();
    });

    root.querySelector('[data-action="refresh"]')?.addEventListener("click", () => {
      state.notice = "";
      loadAll();
    });

    root.querySelector('[data-action="auto-run"]')?.addEventListener("click", async () => {
      const rek = selectedRekening();
      if (!rek || rek.is_cash) return;
      state.mutatingAction = true;
      state.error = "";
      state.notice = "";
      render();
      try {
        const res = await apiJson(
          "/rekonsiliasi/auto-run",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rekening_id: Number(rek.id) }),
          },
          onUnauthorized
        );
        state.notice = `Auto-rekonsiliasi selesai (${res.matched_transactions} transaksi baru cocok).`;
      } catch (err) {
        state.error = err.message || "Auto-rekonsiliasi gagal dijalankan.";
      } finally {
        state.mutatingAction = false;
        await loadAll();
      }
    });

    root.querySelector('[data-action="download"]')?.addEventListener("click", async () => {
      const report = computeEffectiveReport();
      if (!report) return;
      state.downloading = true;
      state.error = "";
      render();
      try {
        const params = new URLSearchParams({
          rekening_id: String(report.rekening.id),
          month: String(report.month),
        });
        if (state.saldoAwalManual !== null) {
          params.set("saldo_awal", String(round2(state.saldoAwalManual)));
        }
        const res = await apiFetch(`/rekonsiliasi/export?${params.toString()}`, {}, onUnauthorized);
        if (!res.ok) {
          let msg = "Gagal membuat file Excel.";
          try {
            msg = parseError(await res.json(), msg);
          } catch {
            // ignore
          }
          throw new Error(msg);
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = report.file_name || "Cash_Report.xlsx";
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (err) {
        state.error = err.message || "Gagal membuat file Excel.";
      } finally {
        state.downloading = false;
        render();
      }
    });

    root.querySelector("[data-dismiss-notice]")?.addEventListener("click", () => {
      state.notice = "";
      render();
    });

    root.querySelectorAll("[data-recon-subtab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.reconSubTab = btn.dataset.reconSubtab;
        render();
      });
    });

    root.querySelectorAll("[data-recon-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.reconFilter = btn.dataset.reconFilter;
        render();
      });
    });

    root.querySelector("[data-recon-search]")?.addEventListener("input", (e) => {
      state.reconSearch = e.target.value;
      const listBox = root.querySelector("[data-recon-list]");
      const report = computeEffectiveReport();
      if (listBox && report) listBox.innerHTML = renderReconcileBody(report);
    });

    root.querySelector("[data-report-search]")?.addEventListener("input", (e) => {
      state.reportSearch = e.target.value;
      const listBox = root.querySelector("[data-report-list]");
      const report = computeEffectiveReport();
      if (listBox && report) listBox.innerHTML = renderCashReportBody(report);
    });

    root.addEventListener("click", async (e) => {
      const report = state.report;
      if (!report) return;

      const galleryBtn = e.target.closest("[data-open-gallery]");
      if (galleryBtn) {
        const tx = report.rows.find((r) => Number(r.id) === Number(galleryBtn.dataset.openGallery));
        if (tx) openGalleryModal(tx);
        return;
      }

      const matchMutBtn = e.target.closest("[data-match-mutasi]");
      if (matchMutBtn) {
        const mut = report.mutasi_rows.find((m) => Number(m.id) === Number(matchMutBtn.dataset.matchMutasi));
        if (mut) openMatchFromMutasiModal(mut);
        return;
      }

      const matchTxBtn = e.target.closest("[data-match-tx]");
      if (matchTxBtn) {
        const tx = report.rows.find((r) => Number(r.id) === Number(matchTxBtn.dataset.matchTx));
        if (tx) openMatchFromTxModal(tx);
        return;
      }

      const adjustBtn = e.target.closest("[data-adjust-mutasi]");
      if (adjustBtn) {
        const mut = report.mutasi_rows.find((m) => Number(m.id) === Number(adjustBtn.dataset.adjustMutasi));
        if (mut) openPenyesuaianModal(mut);
        return;
      }

      const unmatchBtn = e.target.closest("[data-unmatch-group]");
      if (unmatchBtn) {
        const groupId = unmatchBtn.dataset.unmatchGroup;
        if (!groupId || !window.confirm("Lepas tautan rekonsiliasi ini?")) return;
        state.mutatingAction = true;
        state.error = "";
        state.notice = "";
        render();
        try {
          await apiJson(`/rekonsiliasi/match/${encodeURIComponent(groupId)}`, { method: "DELETE" }, onUnauthorized);
          state.notice = "Tautan rekonsiliasi berhasil dilepas.";
        } catch (err) {
          state.error = err.message || "Gagal melepas tautan.";
        } finally {
          state.mutatingAction = false;
          await loadAll();
        }
        return;
      }

      const delBtn = e.target.closest("[data-delete-penyesuaian]");
      if (delBtn) {
        const tid = Number(delBtn.dataset.deletePenyesuaian);
        if (!tid || !window.confirm(`Hapus transaksi penyesuaian #${tid}?`)) return;
        state.mutatingAction = true;
        state.error = "";
        state.notice = "";
        render();
        try {
          await apiJson(`/rekonsiliasi/penyesuaian/${tid}`, { method: "DELETE" }, onUnauthorized);
          state.notice = `Penyesuaian #${tid} berhasil dihapus.`;
        } catch (err) {
          state.error = err.message || "Gagal menghapus penyesuaian.";
        } finally {
          state.mutatingAction = false;
          await loadAll();
        }
      }
    });
  }

  await loadAll();
}
