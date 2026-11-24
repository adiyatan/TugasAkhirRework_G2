import { apiFetch } from "../api.js";
import {
  escapeHtml as esc,
  formatAiCostIdr,
  formatAiCostUsd,
  formatTokenCount,
} from "./shared.js";

const GATE_STYLE = {
  PASS: {
    pill: "bg-emerald-100 text-emerald-800",
    banner: "bg-emerald-50/90 border-emerald-200 text-emerald-950",
    dot: "bg-emerald-500",
    label: "PASS · Layak Dipromosikan",
  },
  WARNING: {
    pill: "bg-amber-100 text-amber-800",
    banner: "bg-amber-50/90 border-amber-200 text-amber-950",
    dot: "bg-amber-500",
    label: "WARNING · Perlu Review",
  },
  FAIL: {
    pill: "bg-rose-100 text-rose-800",
    banner: "bg-rose-50/90 border-rose-200 text-rose-950",
    dot: "bg-rose-500",
    label: "FAIL · Tidak Direkomendasikan",
  },
};

const FIELD_LABELS = {
  total_mutasi: "Total Mutasi",
  nominal_pokok: "Nominal Pokok",
  biaya_admin_kode_unik: "Admin / Kode Unik",
  tanggal_transaksi: "Tanggal Transaksi",
  rekening: "Rekening Sumber",
  rekening_tujuan: "Rekening Tujuan",
  tipe: "Tipe Transaksi",
  kategori: "Kategori SOP",
};

const INPUT_CLS =
  "w-full h-10 px-3 rounded-xl bg-white border border-slate-200 text-xs text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition";

function parseError(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail?.message) return data.detail.message;
  if (typeof data.message === "string") return data.message;
  return fallback;
}

function deltaBadge(val, unit = "%", { lowerIsBetter = false } = {}) {
  if (val === undefined || val === null) return "";
  const num = Number(val);
  const isGood = lowerIsBetter ? num <= 0 : num >= 0;
  const cls = num === 0 ? "text-slate-500" : isGood ? "text-emerald-700" : "text-rose-700";
  const sign = num > 0 ? "+" : "";
  return `<span class="font-mono text-[11px] font-semibold ${cls}">${sign}${num}${unit} vs baseline</span>`;
}

export async function renderAiSettingsMenu(container, { onUnauthorized }) {
  const wrapper = document.createElement("section");
  wrapper.className = "view-animate space-y-5 max-w-5xl mx-auto";
  container.innerHTML = "";
  container.appendChild(wrapper);

  const state = {
    view: "eval", // "models" | "eval" — default "models" on first load, switched cleanly
    loading: true,
    error: "",
    notice: "",
    overview: null,
    selectedModel: "",
    customModel: "",
    usdToIdrRate: 16000,
    evalCandidateModel: "",
    evalSampleSize: 4,
    evalCompareBaseline: true,
    isSwitching: false,
    isEvaluating: false,
    activeEval: null,
    evalError: "",
    expandedCases: new Set(),
  };
  state.view = "models";

  async function loadOverview({ preserveSelection = false } = {}) {
    state.loading = true;
    state.error = "";
    render();
    try {
      const res = await apiFetch("/ai/overview", {}, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        throw new Error(parseError(data, "Gagal memuat konfigurasi & evaluasi AI"));
      }
      state.overview = data;
      const activeId = data.active_model?.id || "";
      if (!preserveSelection || !state.selectedModel) {
        const inCatalog = (data.catalog || []).some((c) => c.id === activeId);
        state.selectedModel = inCatalog ? activeId : "__custom__";
        state.customModel = inCatalog ? "" : activeId;
      }
      if (!preserveSelection || !state.evalCandidateModel) {
        const alt = (data.catalog || []).find((c) => c.id !== activeId);
        state.evalCandidateModel = alt ? alt.id : activeId;
      }
      state.usdToIdrRate = Number(data.usd_to_idr_rate || 16000);
      if (!state.activeEval && (data.evaluations || []).length > 0) {
        state.activeEval = data.evaluations[0];
      }
    } catch (err) {
      state.error = err.message || "Gagal memuat data AI";
    } finally {
      state.loading = false;
      render();
    }
  }

  function getTargetSwitchModel() {
    if (state.selectedModel === "__custom__") {
      return state.customModel.trim();
    }
    return state.selectedModel.trim();
  }

  async function handleSwitchModel(modelOverride = null) {
    const targetModel = (modelOverride || getTargetSwitchModel()).trim();
    if (!targetModel) {
      state.error = "Pilih atau masukkan ID model terlebih dahulu.";
      render();
      return;
    }

    const catalogItem = (state.overview?.catalog || []).find((c) => c.id === targetModel);
    const hasPassedEval =
      catalogItem?.evaluated_pass ||
      (state.overview?.evaluations || []).some(
        (r) => r.candidate_model === targetModel && r.gate_decision === "PASS"
      );

    if (!hasPassedEval && targetModel !== state.overview?.active_model?.id) {
      const ok = window.confirm(
        `Model "${targetModel}" belum memiliki hasil evaluasi PASS pada Golden Dataset.\n\nTetap aktifkan model ini sebagai model produksi?`
      );
      if (!ok) return;
    }

    state.isSwitching = true;
    state.error = "";
    state.notice = "";
    render();
    try {
      const res = await apiFetch(
        "/ai/model",
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            model: targetModel,
            usd_to_idr_rate: Number(state.usdToIdrRate || 16000),
          }),
        },
        onUnauthorized
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(parseError(data, "Gagal mengganti model AI"));
      }
      state.notice = data.message || `Model aktif dipindahkan ke ${targetModel}`;
      await loadOverview({ preserveSelection: false });
    } catch (err) {
      state.error = err.message || "Gagal mengganti model AI";
      render();
    } finally {
      state.isSwitching = false;
      render();
    }
  }

  async function handleEvaluate(candidateOverride = null) {
    const candidate = (candidateOverride || state.evalCandidateModel || getTargetSwitchModel()).trim();
    if (!candidate) {
      state.evalError = "Pilih atau masukkan nama model kandidat untuk dievaluasi.";
      render();
      return;
    }
    state.evalCandidateModel = candidate;
    state.view = "eval";
    state.isEvaluating = true;
    state.evalError = "";
    state.notice = "";
    render();

    try {
      const res = await apiFetch(
        "/ai/evaluate",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            candidate_model: candidate,
            sample_size: Number(state.evalSampleSize || 4),
            compare_baseline: Boolean(state.evalCompareBaseline),
          }),
        },
        onUnauthorized
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(parseError(data, "Gagal menjalankan evaluasi AI"));
      }
      state.activeEval = data;
      state.expandedCases = new Set();
      await loadOverview({ preserveSelection: true });
    } catch (err) {
      state.evalError = err.message || "Evaluasi model gagal dijalankan";
      render();
    } finally {
      state.isEvaluating = false;
      render();
    }
  }

  function renderHeader() {
    const evalCount = (state.overview?.evaluations || []).length;
    return `
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2.5 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold uppercase tracking-wide">Management</span>
            <span class="text-[11px] font-mono text-slate-400">Model: ${esc(state.overview?.active_model?.id || "-")}</span>
          </div>
          <h2 class="text-lg font-bold text-slate-900 tracking-tight mt-1">AI Governance &amp; Evaluasi Model</h2>
        </div>

        <div class="inline-flex p-1 rounded-2xl bg-slate-200/75 self-start sm:self-auto">
          <button
            type="button"
            data-switch-tab="models"
            class="h-9 px-4 rounded-xl text-xs font-semibold transition ${
              state.view === "models" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            Model &amp; Biaya
          </button>
          <button
            type="button"
            data-switch-tab="eval"
            class="h-9 px-4 rounded-xl text-xs font-semibold inline-flex items-center gap-1.5 transition ${
              state.view === "eval" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            <span>Evaluasi AI</span>
            ${
              evalCount > 0
                ? `<span class="px-1.5 py-0.5 rounded-full text-[10px] font-bold ${
                    state.view === "eval" ? "bg-slate-900 text-white" : "bg-slate-300/80 text-slate-700"
                  }">${evalCount}</span>`
                : ""
            }
          </button>
        </div>
      </div>
    `;
  }

  function renderModelsAndCostView() {
    const ov = state.overview;
    const active = ov?.active_model || {};
    const catalog = ov?.catalog || [];
    const usage = ov?.usage_summary || {};
    const byFeat = usage.by_feature || {};
    const totalCostIdr = Number(usage.cost_idr || 0);

    const featureRows = [
      { key: "input_struk", label: "Input Struk", bar: "bg-blue-600" },
      { key: "input_mutasi", label: "Input Mutasi PDF", bar: "bg-indigo-600" },
      { key: "ai_eval", label: "Evaluasi Model AI", bar: "bg-amber-500" },
    ];

    return `
      <!-- Hero Model Aktif -->
      <div class="rounded-3xl bg-gradient-to-br from-slate-900 via-slate-900 to-slate-800 text-white p-5 sm:p-6 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div class="space-y-1.5 min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="px-2.5 py-0.5 rounded-full bg-white/15 text-white text-[10px] font-bold uppercase tracking-wider">Model Aktif</span>
            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
              ov?.api_key_configured ? "bg-emerald-500/20 text-emerald-200" : "bg-amber-500/20 text-amber-200"
            }">
              ${ov?.api_key_configured ? "API Key Terpasang" : "VISION_API_KEY Kosong"}
            </span>
          </div>
          <p class="text-lg sm:text-xl font-extrabold tracking-tight truncate">${esc(active.label || active.id || "-")}</p>
          <p class="font-mono text-xs text-slate-300 truncate">${esc(active.id || "-")} · ${esc(active.provider || "-")}</p>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 shrink-0">
          <div class="rounded-2xl bg-white/10 px-3.5 py-2.5">
            <p class="text-[10px] text-slate-300 font-semibold">Tarif Input / 1M</p>
            <p class="font-mono text-sm font-bold mt-0.5">${esc(formatAiCostIdr(active.input_cost_per_1m_idr || 0))}</p>
            <p class="font-mono text-[10px] text-slate-400">$${active.input_cost_per_1m_usd ?? 0}</p>
          </div>
          <div class="rounded-2xl bg-white/10 px-3.5 py-2.5">
            <p class="text-[10px] text-slate-300 font-semibold">Tarif Output / 1M</p>
            <p class="font-mono text-sm font-bold mt-0.5">${esc(formatAiCostIdr(active.output_cost_per_1m_idr || 0))}</p>
            <p class="font-mono text-[10px] text-slate-400">$${active.output_cost_per_1m_usd ?? 0}</p>
          </div>
          <div class="col-span-2 sm:col-span-1 rounded-2xl bg-white/10 px-3.5 py-2.5">
            <p class="text-[10px] text-slate-300 font-semibold">Total Biaya AI</p>
            <p class="font-mono text-sm font-bold mt-0.5">${esc(formatAiCostIdr(totalCostIdr))}</p>
            <p class="font-mono text-[10px] text-slate-400">${formatTokenCount(usage.total_tokens || 0)} tok</p>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <!-- Kiri: Pindah Model -->
        <div class="lg:col-span-7 rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-4">
          <div class="flex items-center justify-between gap-2">
            <div>
              <h3 class="text-sm font-bold text-slate-900">Pindah Model Gemini AI</h3>
              <p class="text-xs text-slate-500">Daftar model Google Gemini yang aktif, atau masukkan ID Gemini LiteLLM kustom.</p>
            </div>
          </div>

          <div class="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden">
            ${catalog
              .map((m) => {
                const isActive = m.id === active.id;
                const isSelected = state.selectedModel === m.id;
                return `
                  <button
                    type="button"
                    data-pick-model="${esc(m.id)}"
                    class="w-full text-left px-4 py-3 flex items-center justify-between gap-3 transition ${
                      isSelected ? "bg-blue-50/70" : "bg-white hover:bg-slate-50/80"
                    }"
                  >
                    <div class="flex items-start gap-3 min-w-0">
                      <span class="mt-1 w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${
                        isSelected ? "border-blue-600" : "border-slate-300"
                      }">
                        ${isSelected ? `<span class="w-2 h-2 rounded-full bg-blue-600"></span>` : ""}
                      </span>
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-1.5">
                          <span class="text-xs font-bold text-slate-900">${esc(m.label)}</span>
                          <span class="text-[10px] font-semibold text-slate-500">· ${esc(m.tier)}</span>
                          ${m.evaluated_pass ? `<span class="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[9px] font-bold">PASS</span>` : ""}
                          ${isActive ? `<span class="px-1.5 py-0.5 rounded bg-slate-900 text-white text-[9px] font-bold">AKTIF</span>` : ""}
                        </div>
                        <p class="font-mono text-[11px] text-slate-500 truncate mt-0.5">${esc(m.id)}</p>
                      </div>
                    </div>

                    <div class="text-right font-mono text-[11px] shrink-0">
                      <p class="font-semibold text-slate-800">$${m.input_cost_per_1m_usd} / $${m.output_cost_per_1m_usd}</p>
                      <p class="text-[10px] text-slate-400">per 1M tok</p>
                    </div>
                  </button>
                `;
              })
              .join("")}
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-12 gap-3 pt-1">
            <div class="sm:col-span-8">
              <label class="block text-[11px] font-semibold text-slate-600 mb-1">Model ID Gemini (Terpilih / Kustom)</label>
              <input
                type="text"
                data-custom-model-input
                value="${esc(state.selectedModel === "__custom__" ? state.customModel : getTargetSwitchModel())}"
                placeholder="cth: gemini/gemini-3.8-flash"
                class="${INPUT_CLS} font-mono bg-slate-50/70"
              />
            </div>
            <div class="sm:col-span-4">
              <label class="block text-[11px] font-semibold text-slate-600 mb-1">Kurs USD → IDR</label>
              <input
                type="number"
                min="1000"
                step="100"
                data-rate-input
                value="${esc(state.usdToIdrRate)}"
                class="${INPUT_CLS} font-mono bg-slate-50/70"
              />
            </div>
          </div>

          <div class="flex flex-wrap items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button
              type="button"
              data-eval-selected-btn
              ${state.isEvaluating ? "disabled" : ""}
              class="h-10 px-4 rounded-xl border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 text-indigo-800 text-xs font-bold transition disabled:opacity-50"
            >
              ${state.isEvaluating ? "Mengevaluasi..." : "Uji di Evaluasi AI →"}
            </button>
            <button
              type="button"
              data-activate-model-btn
              ${state.isSwitching ? "disabled" : ""}
              class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold shadow-xs transition disabled:opacity-50"
            >
              ${state.isSwitching ? "Menyimpan..." : "Aktifkan Model"}
            </button>
          </div>
        </div>

        <!-- Kanan: Ringkasan Biaya & Token -->
        <div class="lg:col-span-5 rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-4">
          <div>
            <h3 class="text-sm font-bold text-slate-900">Biaya Penggunaan Token AI</h3>
            <p class="text-xs text-slate-500">Akumulasi seluruh pemanggilan Vision AI di sistem.</p>
          </div>

          <div class="grid grid-cols-2 gap-2.5">
            <div class="rounded-2xl bg-slate-50 border border-slate-200/70 p-3.5">
              <p class="text-[11px] font-semibold text-slate-500">Total Biaya</p>
              <p class="font-mono text-lg font-extrabold text-slate-900 mt-0.5">${esc(formatAiCostIdr(totalCostIdr))}</p>
              <p class="font-mono text-[11px] text-slate-400">${esc(formatAiCostUsd(usage.cost_usd || 0))}</p>
            </div>
            <div class="rounded-2xl bg-slate-50 border border-slate-200/70 p-3.5">
              <p class="text-[11px] font-semibold text-slate-500">Total Token</p>
              <p class="font-mono text-lg font-extrabold text-slate-900 mt-0.5">${formatTokenCount(usage.total_tokens || 0)}</p>
              <p class="font-mono text-[11px] text-slate-400">${formatTokenCount(usage.total_calls || 0)}x panggilan AI</p>
            </div>
          </div>

          <div class="space-y-3 pt-2 border-t border-slate-100">
            <p class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Distribusi per Fitur</p>
            ${featureRows
              .map((fr) => {
                const stat = byFeat[fr.key] || { calls: 0, total_tokens: 0, cost_idr: 0 };
                const pct = totalCostIdr > 0 ? Math.max(4, Math.round((stat.cost_idr / totalCostIdr) * 100)) : 0;
                return `
                  <div class="space-y-1.5">
                    <div class="flex items-center justify-between gap-2 text-xs">
                      <span class="font-semibold text-slate-800">${esc(fr.label)} <span class="text-slate-400 font-normal">(${stat.calls}x)</span></span>
                      <span class="font-mono font-bold text-slate-900">${esc(formatAiCostIdr(stat.cost_idr))}</span>
                    </div>
                    <div class="h-1.5 rounded-full bg-slate-100 overflow-hidden">
                      <div class="h-full rounded-full ${fr.bar}" style="width: ${stat.cost_idr > 0 ? pct : 0}%"></div>
                    </div>
                    <p class="font-mono text-[10px] text-slate-400">${formatTokenCount(stat.total_tokens)} token</p>
                  </div>
                `;
              })
              .join("")}
          </div>

          <div class="rounded-2xl bg-emerald-50/70 border border-emerald-200/70 px-3.5 py-2.5 text-[11px] text-emerald-900">
            <strong>Hemat Biaya:</strong> PDF teks BRI diproses parser deterministik (<strong>Rp0 · 0 token</strong>).
          </div>
        </div>
      </div>
    `;
  }

  function renderEvalResult(evalRun) {
    if (state.isEvaluating) {
      return `
        <div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center space-y-2 shadow-2xs">
          <div class="w-10 h-10 rounded-2xl bg-indigo-50 text-indigo-600 mx-auto flex items-center justify-center animate-pulse">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 0 1-.659 1.591L5 14.5M14.25 3.104v5.714c0 .597.237 1.17.659 1.591L19.8 15.3" />
            </svg>
          </div>
          <p class="text-sm font-bold text-slate-900">Menjalankan Evaluasi Golden Dataset...</p>
          <p class="text-xs text-slate-500">Menguji <span class="font-mono font-semibold">${esc(state.evalCandidateModel)}</span> pada ${state.evalSampleSize} struk terverifikasi.</p>
        </div>
      `;
    }

    if (!evalRun) {
      return `
        <div class="rounded-3xl bg-white border border-dashed border-slate-300 p-10 text-center space-y-2">
          <p class="text-sm font-bold text-slate-800">Belum Ada Hasil Evaluasi</p>
          <p class="text-xs text-slate-500 max-w-md mx-auto">
            Pilih model kandidat di atas lalu klik <strong>Jalankan Evaluasi</strong> untuk menguji akurasi, kepatuhan skema JSON, dan biaya terhadap model aktif.
          </p>
        </div>
      `;
    }

    const summary = evalRun.summary || {};
    const details = evalRun.details || [];
    const comp = summary.comparison;
    const gate = GATE_STYLE[evalRun.gate_decision] || GATE_STYLE.WARNING;
    const fieldAcc = summary.field_accuracy || {};
    const reasons = summary.gate_reasons || [];
    const activeId = state.overview?.active_model?.id;

    return `
      <!-- Verdict Banner -->
      <div class="rounded-3xl border p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 ${gate.banner}">
        <div class="space-y-1.5 min-w-0">
          <div class="flex flex-wrap items-center gap-2">
            <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold ${gate.pill}">
              <span class="w-1.5 h-1.5 rounded-full ${gate.dot}"></span>
              ${esc(gate.label)}
            </span>
            <span class="font-mono text-xs font-bold">${esc(evalRun.candidate_model)}</span>
            <span class="text-xs opacity-75">· ${evalRun.sample_count} kasus uji</span>
          </div>
          ${reasons.length ? `<p class="text-xs leading-relaxed">${esc(reasons.join(" "))}</p>` : ""}
        </div>

        <div class="shrink-0">
          ${
            evalRun.candidate_model !== activeId
              ? `<button type="button" data-promote-model="${esc(evalRun.candidate_model)}" class="h-10 px-4 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold shadow-xs transition">
                  Promosikan Jadi Model Aktif
                </button>`
              : `<span class="inline-flex items-center h-9 px-3.5 rounded-xl bg-slate-900 text-white text-xs font-bold">Model Sedang Aktif</span>`
          }
        </div>
      </div>

      <!-- 4 KPI Cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div class="rounded-2xl bg-white border border-slate-200/90 p-4 shadow-2xs space-y-1">
          <p class="text-[11px] font-semibold text-slate-500">Critical Pass Rate</p>
          <p class="font-mono text-2xl font-extrabold text-slate-900 tabular-nums">${summary.critical_pass_pct ?? 0}%</p>
          <div>${comp ? deltaBadge(comp.delta_critical_pass_pct, "%") : `<span class="text-[11px] text-slate-400">Field finansial utama</span>`}</div>
        </div>

        <div class="rounded-2xl bg-white border border-slate-200/90 p-4 shadow-2xs space-y-1">
          <p class="text-[11px] font-semibold text-slate-500">Akurasi Field</p>
          <p class="font-mono text-2xl font-extrabold text-slate-900 tabular-nums">${summary.overall_field_accuracy_pct ?? 0}%</p>
          <div>${comp ? deltaBadge(comp.delta_field_accuracy_pct, "%") : `<span class="text-[11px] text-slate-400">Rata-rata 8 field</span>`}</div>
        </div>

        <div class="rounded-2xl bg-white border border-slate-200/90 p-4 shadow-2xs space-y-1">
          <p class="text-[11px] font-semibold text-slate-500">Skema &amp; Aturan SOP</p>
          <p class="font-mono text-2xl font-extrabold text-slate-900 tabular-nums">${summary.schema_validity_pct ?? 0}%</p>
          <p class="font-mono text-[11px] text-slate-500">Rule pass ${summary.rule_pass_pct ?? 0}%</p>
        </div>

        <div class="rounded-2xl bg-white border border-slate-200/90 p-4 shadow-2xs space-y-1">
          <p class="text-[11px] font-semibold text-slate-500">Biaya &amp; Latensi / Struk</p>
          <p class="font-mono text-2xl font-extrabold text-indigo-700 tabular-nums">${esc(formatAiCostIdr(summary.avg_cost_idr_per_receipt || 0))}</p>
          <p class="font-mono text-[11px] text-slate-500">
            ${summary.avg_latency_ms ?? 0} ms · ${formatTokenCount(summary.total_tokens || 0)} tok
          </p>
        </div>
      </div>

      <!-- Field Accuracy + Per-Case Breakdown -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        <!-- Kiri: Akurasi per Field -->
        <div class="lg:col-span-5 rounded-3xl bg-white border border-slate-200/90 p-5 shadow-2xs space-y-3.5">
          <div>
            <h4 class="text-sm font-bold text-slate-900">Akurasi per Field</h4>
            <p class="text-xs text-slate-500">Perbandingan output model vs Ground Truth.</p>
          </div>
          <div class="space-y-2.5">
            ${Object.entries(FIELD_LABELS)
              .map(([key, label]) => {
                const pct = Number(fieldAcc[key] ?? 0);
                const barCls = pct >= 90 ? "bg-emerald-500" : pct >= 70 ? "bg-amber-500" : "bg-rose-500";
                return `
                  <div class="space-y-1">
                    <div class="flex items-center justify-between text-xs">
                      <span class="font-medium text-slate-700">${esc(label)}</span>
                      <span class="font-mono font-bold text-slate-900 tabular-nums">${pct}%</span>
                    </div>
                    <div class="h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div class="h-full rounded-full ${barCls} transition-all duration-300" style="width: ${pct}%"></div>
                    </div>
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>

        <!-- Kanan: Hasil per Kasus Uji -->
        <div class="lg:col-span-7 rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
          <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-2">
            <div>
              <h4 class="text-sm font-bold text-slate-900">Hasil Kasus Uji (${details.length})</h4>
              <p class="text-xs text-slate-500">Klik <strong>Detail</strong> pada baris untuk melihat perbandingan Expected vs Actual.</p>
            </div>
          </div>

          <div class="divide-y divide-slate-100">
            ${details
              .map((c) => {
                const isExpanded = state.expandedCases.has(c.case_id);
                const fields = c.fields || {};
                const mismatches = Object.entries(fields).filter(([, fv]) => !fv.match);
                return `
                  <div class="px-5 py-3.5 space-y-2.5">
                    <div class="flex items-start justify-between gap-3">
                      <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-1.5">
                          <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            c.critical_pass ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
                          }">${c.critical_pass ? "PASS" : "FAIL"}</span>
                          <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-bold uppercase">${esc(c.tab_type)}</span>
                          <span class="text-xs font-bold text-slate-900 truncate">${esc(c.title)}</span>
                        </div>
                        <p class="text-[11px] mt-1 ${
                          c.error ? "text-rose-600 font-medium" : mismatches.length ? "text-amber-700" : "text-slate-500"
                        }">
                          ${
                            c.error
                              ? esc(c.error)
                              : mismatches.length
                                ? `${mismatches.length} field berbeda (${mismatches.map(([k]) => FIELD_LABELS[k] || k).join(", ")})`
                                : "Semua 8 field cocok · JSON & aturan SOP valid"
                          }
                        </p>
                      </div>

                      <div class="flex items-center gap-2 shrink-0">
                        <div class="text-right font-mono text-[11px]">
                          <p class="font-bold text-slate-900">${c.field_accuracy_pct}%</p>
                          <p class="text-[10px] text-slate-400">${esc(formatAiCostIdr(c.usage?.cost_idr || 0))}</p>
                        </div>
                        <button
                          type="button"
                          data-toggle-case="${esc(c.case_id)}"
                          class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-[11px] font-semibold text-slate-700 transition"
                        >
                          ${isExpanded ? "Tutup ▴" : "Detail ▾"}
                        </button>
                      </div>
                    </div>

                    ${
                      isExpanded
                        ? `<div class="rounded-2xl bg-slate-50 border border-slate-200/80 p-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px]">
                            ${Object.entries(fields)
                              .map(
                                ([k, fv]) => `
                                  <div class="rounded-xl px-2.5 py-1.5 flex items-center justify-between gap-2 ${
                                    fv.match ? "bg-white border border-slate-200/70" : "bg-rose-50 border border-rose-200"
                                  }">
                                    <span class="font-semibold text-slate-600 shrink-0">${esc(FIELD_LABELS[k] || k)}</span>
                                    <span class="font-mono text-right truncate">
                                      ${
                                        fv.match
                                          ? `<span class="text-emerald-700">${esc(fv.actual ?? "null")}</span>`
                                          : `<span class="text-rose-600 line-through mr-1">${esc(fv.actual ?? "null")}</span><span class="text-emerald-800 font-bold">→ ${esc(fv.expected ?? "null")}</span>`
                                      }
                                    </span>
                                  </div>
                                `
                              )
                              .join("")}
                          </div>`
                        : ""
                    }
                  </div>
                `;
              })
              .join("")}
          </div>
        </div>
      </div>
    `;
  }

  function renderEvalView() {
    const ov = state.overview;
    const catalog = ov?.catalog || [];
    const active = ov?.active_model || {};
    const evalHistory = ov?.evaluations || [];

    return `
      <!-- Control Bar Evaluasi -->
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-4">
        <div class="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
          <div class="sm:col-span-5">
            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Model Kandidat</label>
            <select data-eval-model-select class="${INPUT_CLS} font-mono">
              ${catalog
                .map(
                  (m) =>
                    `<option value="${esc(m.id)}" ${state.evalCandidateModel === m.id ? "selected" : ""}>${esc(m.label)} (${esc(m.id)})</option>`
                )
                .join("")}
              ${
                !catalog.some((m) => m.id === state.evalCandidateModel) && state.evalCandidateModel
                  ? `<option value="${esc(state.evalCandidateModel)}" selected>${esc(state.evalCandidateModel)}</option>`
                  : ""
              }
            </select>
          </div>

          <div class="sm:col-span-4">
            <label class="block text-[11px] font-semibold text-slate-600 mb-1">Golden Dataset (Bukti Terverifikasi)</label>
            <select data-eval-size-select class="${INPUT_CLS}">
              <option value="4" ${Number(state.evalSampleSize) === 4 ? "selected" : ""}>4 Kasus Inti (Normal, Flip, Pindah Buku, Reimburse)</option>
              <option value="7" ${Number(state.evalSampleSize) === 7 ? "selected" : ""}>7 Kasus Lengkap (+ Masuk, Pindah Normal, Slip Gaji)</option>
            </select>
          </div>

          <div class="sm:col-span-3">
            <button
              type="button"
              data-run-eval-btn
              ${state.isEvaluating ? "disabled" : ""}
              class="w-full h-10 px-4 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs transition"
            >
              ${state.isEvaluating ? "Menjalankan..." : "Jalankan Evaluasi"}
            </button>
          </div>
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 text-xs">
          <label class="inline-flex items-center gap-2 text-slate-700 cursor-pointer">
            <input type="checkbox" data-eval-compare-cb ${state.evalCompareBaseline ? "checked" : ""} class="rounded border-slate-300" />
            <span>Bandingkan langsung dengan baseline aktif (<span class="font-mono font-semibold text-slate-900">${esc(active.id || "-")}</span>)</span>
          </label>
          <span class="text-[11px] text-slate-400">Gate PASS: JSON 100% · Finansial Kritis ≥ 80% · 0 Regresi</span>
        </div>

        ${
          state.evalError
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs font-semibold text-rose-700">${esc(state.evalError)}</div>`
            : ""
        }
      </div>

      ${renderEvalResult(state.activeEval)}

      ${
        evalHistory.length
          ? `<div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
              <div class="px-5 py-4 border-b border-slate-100">
                <h4 class="text-sm font-bold text-slate-900">Riwayat Benchmark (${evalHistory.length})</h4>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      <th class="py-2.5 pl-5 pr-3">Model Kandidat</th>
                      <th class="py-2.5 px-3">Gate</th>
                      <th class="py-2.5 px-3 text-right">Pass Rate</th>
                      <th class="py-2.5 px-3 text-right">Field Acc</th>
                      <th class="py-2.5 px-3 text-right">Biaya Uji</th>
                      <th class="py-2.5 pl-3 pr-5 text-right">Aksi</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    ${evalHistory
                      .map((run) => {
                        const badge = GATE_STYLE[run.gate_decision] || GATE_STYLE.WARNING;
                        const isSelected = state.activeEval?.id === run.id;
                        return `
                          <tr class="${isSelected ? "bg-indigo-50/40" : "hover:bg-slate-50/70"}">
                            <td class="py-2.5 pl-5 pr-3">
                              <p class="font-mono font-bold text-slate-900">#${run.id} · ${esc(run.candidate_model)}</p>
                              <p class="text-[11px] text-slate-400">Baseline: ${esc(run.baseline_model)} · ${run.sample_count} kasus</p>
                            </td>
                            <td class="py-2.5 px-3">
                              <span class="px-2 py-0.5 rounded-full text-[10px] font-bold ${badge.pill}">${esc(run.gate_decision)}</span>
                            </td>
                            <td class="py-2.5 px-3 text-right font-mono font-bold text-slate-900">${run.summary?.critical_pass_pct ?? 0}%</td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-700">${run.summary?.overall_field_accuracy_pct ?? 0}%</td>
                            <td class="py-2.5 px-3 text-right font-mono text-slate-700">${esc(formatAiCostIdr(run.summary?.total_cost_idr || 0))}</td>
                            <td class="py-2.5 pl-3 pr-5 text-right">
                              <button type="button" data-select-eval="${run.id}" class="h-7 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-[11px] font-semibold text-slate-700">
                                ${isSelected ? "Ditampilkan" : "Lihat"}
                              </button>
                            </td>
                          </tr>
                        `;
                      })
                      .join("")}
                  </tbody>
                </table>
              </div>
            </div>`
          : ""
      }
    `;
  }

  function render() {
    if (state.loading && !state.overview) {
      wrapper.innerHTML = `<div class="rounded-3xl bg-white border border-slate-200/90 p-10 text-center text-xs text-slate-400">Memuat manajemen model &amp; evaluasi AI...</div>`;
      return;
    }

    wrapper.innerHTML = `
      ${renderHeader()}

      ${
        state.error
          ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs font-semibold text-rose-700">${esc(state.error)}</div>`
          : ""
      }
      ${
        state.notice
          ? `<div class="rounded-2xl bg-emerald-50 border border-emerald-200 px-4 py-3 text-xs font-semibold text-emerald-800">${esc(state.notice)}</div>`
          : ""
      }

      ${state.view === "models" ? renderModelsAndCostView() : renderEvalView()}
    `;

    bindEvents();
  }

  function bindEvents() {
    wrapper.querySelectorAll("[data-switch-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.view = btn.dataset.switchTab;
        render();
      });
    });

    wrapper.querySelectorAll("[data-pick-model]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedModel = btn.dataset.pickModel || "";
        state.evalCandidateModel = state.selectedModel;
        render();
      });
    });

    wrapper.querySelector("[data-custom-model-input]")?.addEventListener("input", (e) => {
      const val = e.target.value;
      const inCatalog = (state.overview?.catalog || []).some((c) => c.id === val.trim());
      if (inCatalog) {
        state.selectedModel = val.trim();
        state.customModel = "";
      } else {
        state.selectedModel = "__custom__";
        state.customModel = val;
      }
      if (val.trim()) {
        state.evalCandidateModel = val.trim();
      }
    });

    wrapper.querySelector("[data-rate-input]")?.addEventListener("input", (e) => {
      state.usdToIdrRate = Number(e.target.value || 16000);
    });

    wrapper.querySelector("[data-activate-model-btn]")?.addEventListener("click", () => handleSwitchModel());
    wrapper.querySelector("[data-eval-selected-btn]")?.addEventListener("click", () => handleEvaluate(getTargetSwitchModel()));

    wrapper.querySelector("[data-eval-model-select]")?.addEventListener("change", (e) => {
      state.evalCandidateModel = e.target.value;
    });
    wrapper.querySelector("[data-eval-size-select]")?.addEventListener("change", (e) => {
      state.evalSampleSize = Number(e.target.value || 4);
    });
    wrapper.querySelector("[data-eval-compare-cb]")?.addEventListener("change", (e) => {
      state.evalCompareBaseline = Boolean(e.target.checked);
    });
    wrapper.querySelector("[data-run-eval-btn]")?.addEventListener("click", () => handleEvaluate());

    wrapper.querySelector("[data-promote-model]")?.addEventListener("click", (e) => {
      handleSwitchModel(e.currentTarget.dataset.promoteModel);
    });

    wrapper.querySelectorAll("[data-select-eval]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.selectEval);
        const found = (state.overview?.evaluations || []).find((r) => r.id === id);
        if (found) {
          state.activeEval = found;
          state.expandedCases = new Set();
          render();
        }
      });
    });

    wrapper.querySelectorAll("[data-toggle-case]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cid = btn.dataset.toggleCase;
        if (state.expandedCases.has(cid)) {
          state.expandedCases.delete(cid);
        } else {
          state.expandedCases.add(cid);
        }
        render();
      });
    });
  }

  await loadOverview();
}
