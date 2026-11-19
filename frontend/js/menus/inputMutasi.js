import { apiFetch } from "../api.js";

const INPUT_CLS =
  "w-full h-10 px-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 disabled:bg-slate-100 disabled:text-slate-500 transition";

const STATUS_BADGE = {
  BELUM_REKON: { cls: "bg-slate-100 text-slate-700", label: "Belum Rekon" },
  BELUM_TERCATAT: { cls: "bg-amber-50 text-amber-800", label: "Belum Tercatat" },
  SESUAI: { cls: "bg-emerald-50 text-emerald-700", label: "Sesuai Struk" },
  SELISIH_KODE_UNIK_ADMIN: { cls: "bg-blue-50 text-blue-700", label: "Cocok (Selisih Admin)" },
  PINDAH_BUKU: { cls: "bg-indigo-50 text-indigo-700", label: "Pindah Buku" },
};

const ICON_UPLOAD = `<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>`;
const ICON_PDF = `<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M7 3h7l5 5v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M14 3v5h5M9 13h6M9 17h4"/></svg>`;
const ICON_EDIT = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 3.487a2.1 2.1 0 1 1 2.97 2.97L7.5 18.79 3 20l1.21-4.5L16.862 3.487Z"/></svg>`;
const ICON_TRASH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/></svg>`;
const ICON_REFRESH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h5M20 20v-5h-5M5.5 9A7.5 7.5 0 0 1 19 6.5M18.5 15A7.5 7.5 0 0 1 5 17.5"/></svg>`;
const ICON_SEARCH = `<svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>`;

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
  return `Rp${Math.round(Number(amount || 0)).toLocaleString("id-ID")}`;
}

function normalizeTime(value) {
  const cleaned = String(value || "").replace(/\s*WIB\b/i, "").trim();
  if (/^\d{2}:\d{2}$/.test(cleaned)) return `${cleaned}:00`;
  if (/^\d{2}:\d{2}:\d{2}$/.test(cleaned)) return cleaned;
  return "00:00:00";
}

function parseError(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail?.message) return data.detail.message;
  return data.message || fallback;
}

function computeClientSummary(rows, printedSaldoAwal = null, printedSaldoAkhir = null) {
  const mismatchIndices = new Set();
  if (!rows.length) {
    return {
      periode_mulai: "-",
      periode_selesai: "-",
      saldo_awal_periode: null,
      total_cr: 0,
      total_db: 0,
      saldo_akhir_periode: null,
      selisih_saldo: null,
      printed_mismatch: "",
      mismatchIndices,
      balance_valid: true,
    };
  }
  const dates = rows.map((r) => r.tanggal).filter(Boolean).sort();
  const total_cr = rows.reduce((s, r) => s + (r.tipe === "CR" ? Number(r.nominal || 0) : 0), 0);
  const total_db = rows.reduce((s, r) => s + (r.tipe === "DB" ? Number(r.nominal || 0) : 0), 0);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const saldo_awal =
    first.saldo !== null && first.saldo !== undefined && first.saldo !== ""
      ? first.tipe === "CR"
        ? Number(first.saldo) - Number(first.nominal || 0)
        : Number(first.saldo) + Number(first.nominal || 0)
      : null;
  const saldo_akhir =
    last.saldo !== null && last.saldo !== undefined && last.saldo !== ""
      ? Number(last.saldo)
      : null;

  let selisih = null;
  let balance_valid = true;
  let printed_mismatch = "";

  if (saldo_awal !== null && saldo_akhir !== null) {
    const expected = saldo_awal + total_cr - total_db;
    selisih = Math.round((saldo_akhir - expected) * 100) / 100;
    balance_valid = Math.abs(selisih) <= 0.01;

    let running = saldo_awal;
    rows.forEach((r, idx) => {
      running = r.tipe === "CR" ? running + Number(r.nominal || 0) : running - Number(r.nominal || 0);
      if (r.saldo !== null && r.saldo !== undefined && r.saldo !== "") {
        if (Math.abs(running - Number(r.saldo)) > 0.01) {
          mismatchIndices.add(idx);
          balance_valid = false;
        }
      }
    });
  }

  if (
    printedSaldoAwal !== null &&
    printedSaldoAwal !== undefined &&
    saldo_awal !== null &&
    Math.abs(Number(printedSaldoAwal) - saldo_awal) > 0.01
  ) {
    balance_valid = false;
    printed_mismatch = "Saldo awal tidak cocok dengan PDF";
  } else if (
    printedSaldoAkhir !== null &&
    printedSaldoAkhir !== undefined &&
    saldo_akhir !== null &&
    Math.abs(Number(printedSaldoAkhir) - saldo_akhir) > 0.01
  ) {
    balance_valid = false;
    printed_mismatch = "Saldo akhir tidak cocok dengan PDF";
  }

  return {
    periode_mulai: dates[0] || "-",
    periode_selesai: dates[dates.length - 1] || "-",
    saldo_awal_periode: saldo_awal,
    total_cr,
    total_db,
    saldo_akhir_periode: saldo_akhir,
    selisih_saldo: selisih,
    printed_mismatch,
    mismatchIndices,
    balance_valid,
  };
}

export async function renderInputMutasiMenu(container, { onUnauthorized }) {
  const state = {
    view: "upload", // "upload" | "batches" | "rows"
    step: 1, // 1: upload PDF, 2: preview & cek saldo, 3: selesai
    metadata: [],
    selectedRekeningId: "AUTO",
    selectedFile: null,
    isExtracting: false,
    extractError: "",
    previewData: null,
    editableRows: [],
    previewSearch: "",
    showOnlyMismatch: false,
    replaceExisting: false,
    isSaving: false,
    saveError: "",
    saveResult: null,
    batches: [],
    batchSearch: "",
    rows: [],
    rowFilters: {
      rekening_id: "",
      batch_id: "",
      tipe: "",
      status_rekonsiliasi: "",
      tanggal_mulai: "",
      tanggal_selesai: "",
      search: "",
    },
    listNotice: "",
    listError: "",
  };
  let rowSearchTimer = null;

  async function loadMetadata() {
    const res = await apiFetch("/mutasi/metadata", {}, onUnauthorized);
    const data = await res.json();
    if (!res.ok) throw new Error(parseError(data, "Gagal memuat metadata mutasi"));
    state.metadata = data.rekening_perusahaan || [];
  }

  async function loadBatches() {
    try {
      const res = await apiFetch("/mutasi/batches?limit=50", {}, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        state.listError = parseError(data, "Gagal memuat riwayat batch");
        return;
      }
      state.batches = data.items || [];
      state.listError = "";
    } catch (err) {
      state.listError = err.message || "Gagal memuat riwayat batch";
    }
  }

  async function loadRows() {
    const params = new URLSearchParams();
    if (state.rowFilters.rekening_id) params.set("rekening_id", state.rowFilters.rekening_id);
    if (state.rowFilters.batch_id) params.set("batch_id", state.rowFilters.batch_id);
    if (state.rowFilters.tipe) params.set("tipe", state.rowFilters.tipe);
    if (state.rowFilters.status_rekonsiliasi) {
      params.set("status_rekonsiliasi", state.rowFilters.status_rekonsiliasi);
    }
    if (state.rowFilters.tanggal_mulai) params.set("tanggal_mulai", state.rowFilters.tanggal_mulai);
    if (state.rowFilters.tanggal_selesai) params.set("tanggal_selesai", state.rowFilters.tanggal_selesai);
    if (state.rowFilters.search.trim()) params.set("search", state.rowFilters.search.trim());
    params.set("limit", "200");

    try {
      const res = await apiFetch(`/mutasi/rows?${params.toString()}`, {}, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        state.listError = parseError(data, "Gagal memuat daftar mutasi");
        return;
      }
      state.rows = data.items || [];
      state.listError = "";
    } catch (err) {
      state.listError = err.message || "Gagal memuat daftar mutasi";
    }
  }

  function resetWizard() {
    state.view = "upload";
    state.step = 1;
    state.selectedFile = null;
    state.extractError = "";
    state.previewData = null;
    state.editableRows = [];
    state.previewSearch = "";
    state.showOnlyMismatch = false;
    state.replaceExisting = false;
    state.saveError = "";
    state.saveResult = null;
    state.isExtracting = false;
    state.isSaving = false;
    render();
  }

  function setSelectedPdf(file) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      state.extractError = "File yang dipilih harus berformat .pdf";
      render();
      return;
    }
    state.selectedFile = file;
    state.extractError = "";
    render();
  }

  async function handlePreview() {
    if (!state.selectedFile || state.isExtracting) return;
    state.isExtracting = true;
    state.extractError = "";
    render();

    try {
      const formData = new FormData();
      formData.append("file", state.selectedFile);
      formData.append("rekening_id", state.selectedRekeningId);
      const res = await apiFetch("/mutasi/preview", { method: "POST", body: formData }, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        state.extractError = parseError(data, "Gagal mengekstrak PDF mutasi");
        return;
      }
      state.previewData = data;
      state.editableRows = (data.rows || []).map((r) => ({ ...r }));
      state.previewSearch = "";
      state.showOnlyMismatch = false;
      state.replaceExisting = false;
      state.saveError = "";
      state.step = 2;
    } catch (err) {
      state.extractError = err.message || "Gagal memproses PDF mutasi";
    } finally {
      state.isExtracting = false;
      render();
    }
  }

  async function handleSave() {
    if (!state.previewData || state.isSaving) return;
    if (!state.editableRows.length) {
      state.saveError = "Minimal harus ada 1 baris mutasi untuk disimpan.";
      render();
      return;
    }

    state.isSaving = true;
    state.saveError = "";
    render();

    try {
      const payload = {
        rekening_id: state.previewData.rekening.id,
        no_rekening: state.previewData.detected_no_rekening || null,
        nama_file: state.previewData.nama_file,
        file_hash: state.previewData.file_hash,
        metode_ekstraksi: state.previewData.metode_ekstraksi,
        replace_existing: Boolean(state.replaceExisting),
        rows: state.editableRows.map((r) => ({
          tanggal: String(r.tanggal || "").trim(),
          waktu: normalizeTime(r.waktu),
          uraian: String(r.uraian || "").trim(),
          tipe: r.tipe === "CR" ? "CR" : "DB",
          nominal: Number(r.nominal || 0),
          saldo: r.saldo === "" || r.saldo === null || r.saldo === undefined ? null : Number(r.saldo),
        })),
      };

      const res = await apiFetch(
        "/mutasi/save",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        onUnauthorized
      );
      const data = await res.json();
      if (!res.ok) {
        state.saveError = parseError(data, "Gagal menyimpan batch mutasi");
        return;
      }
      state.saveResult = data;
      state.step = 3;
      await Promise.all([loadBatches(), loadRows()]);
    } catch (err) {
      state.saveError = err.message || "Gagal menyimpan batch mutasi";
    } finally {
      state.isSaving = false;
      render();
    }
  }

  async function handleDeleteBatch(batchId, filename) {
    if (
      !confirm(
        `Hapus Batch #${batchId} (${filename})? Seluruh baris mutasi dan kecocokan rekonsiliasi terkait akan dihitung ulang.`
      )
    ) {
      return;
    }
    try {
      const res = await apiFetch(`/mutasi/batches/${batchId}`, { method: "DELETE" }, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        alert(parseError(data, "Gagal menghapus batch"));
        return;
      }
      state.listNotice = data.message;
      if (Number(state.rowFilters.batch_id) === batchId) {
        state.rowFilters.batch_id = "";
      }
      await Promise.all([loadBatches(), loadRows()]);
      render();
    } catch (err) {
      alert(err.message || "Gagal menghapus batch");
    }
  }

  function openRowModal(rowIdx = null) {
    const isNew = rowIdx === null;
    const existing = isNew ? null : state.editableRows[rowIdx];
    const fallbackDate =
      state.editableRows[state.editableRows.length - 1]?.tanggal ||
      new Date().toISOString().slice(0, 10);
    const initial = existing || {
      tanggal: fallbackDate,
      waktu: "12:00:00",
      uraian: "",
      tipe: "DB",
      nominal: "",
      saldo: "",
      already_exists: false,
    };

    const modal = document.createElement("div");
    modal.className =
      "fixed inset-0 z-50 bg-slate-950/65 backdrop-blur-xs flex items-end sm:items-center justify-center p-0 sm:p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-t-3xl sm:rounded-3xl max-w-lg w-full flex flex-col overflow-hidden shadow-2xl border border-slate-200 modal-panel-animate">
        <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="px-2 py-0.5 rounded-lg bg-slate-900 text-white font-mono text-xs font-bold">
              ${isNew ? "+ Baru" : `#${rowIdx + 1}`}
            </span>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 truncate">
              ${isNew ? "Tambah Baris Mutasi" : "Edit Baris Mutasi"}
            </h3>
          </div>
          <button type="button" data-close-row-modal class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center">✕</button>
        </div>

        <form data-row-modal-form class="p-5 space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Tanggal</label>
              <input type="date" name="tanggal" value="${esc(initial.tanggal)}" required class="${INPUT_CLS} font-mono" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Waktu (WIB)</label>
              <input type="time" step="1" name="waktu" value="${esc(normalizeTime(initial.waktu))}" required class="${INPUT_CLS} font-mono" />
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Tipe Mutasi</label>
              <select name="tipe" class="${INPUT_CLS} font-bold">
                <option value="CR" ${initial.tipe === "CR" ? "selected" : ""}>CR — Uang Masuk (+)</option>
                <option value="DB" ${initial.tipe === "DB" ? "selected" : ""}>DB — Uang Keluar (-)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-700 mb-1">Nominal (Rp)</label>
              <input type="number" step="0.01" min="0.01" name="nominal" value="${esc(initial.nominal)}" required class="${INPUT_CLS} font-mono" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-xs font-semibold text-slate-700 mb-1">Saldo Berjalan (Opsional)</label>
              <input type="number" step="0.01" name="saldo" value="${initial.saldo ?? ""}" placeholder="Kosongkan jika tidak tercetak" class="${INPUT_CLS} font-mono" />
            </div>
            <div class="sm:col-span-2">
              <label class="block text-xs font-semibold text-slate-700 mb-1">Uraian Transaksi</label>
              <textarea name="uraian" rows="2" required class="w-full p-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition">${esc(initial.uraian || "")}</textarea>
            </div>
          </div>

          <p data-row-modal-err class="hidden rounded-xl bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"></p>

          <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
            <button type="button" data-close-row-modal class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition">Batal</button>
            <button type="submit" class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition">
              ${isNew ? "Tambahkan Baris" : "Simpan Baris"}
            </button>
          </div>
        </form>
      </div>
    `;

    const close = () => modal.remove();
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close-row-modal]")) close();
    });
    document.body.appendChild(modal);

    const form = modal.querySelector("[data-row-modal-form]");
    const errEl = modal.querySelector("[data-row-modal-err]");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      errEl.classList.add("hidden");
      const nominalVal = Number(form.elements["nominal"].value);
      const saldoRaw = form.elements["saldo"].value;
      const uraianVal = String(form.elements["uraian"].value || "").trim();
      if (!(nominalVal > 0) || !uraianVal) {
        errEl.textContent = "Nominal harus > 0 dan uraian tidak boleh kosong.";
        errEl.classList.remove("hidden");
        return;
      }
      const nextRow = {
        tanggal: String(form.elements["tanggal"].value || "").trim(),
        waktu: normalizeTime(form.elements["waktu"].value),
        uraian: uraianVal,
        tipe: form.elements["tipe"].value === "CR" ? "CR" : "DB",
        nominal: nominalVal,
        saldo: saldoRaw === "" ? null : Number(saldoRaw),
        already_exists: false,
      };
      if (isNew) {
        state.editableRows = [...state.editableRows, nextRow];
      } else {
        state.editableRows = state.editableRows.map((r, i) => (i === rowIdx ? nextRow : r));
      }
      close();
      render();
    });
  }

  function renderTopBar() {
    const batchCount = (state.batches || []).length;
    return `
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-lg font-bold text-slate-900 tracking-tight">Input Mutasi Bank</h2>
          <p class="text-xs text-slate-500">Upload rekening koran PDF, cek konsistensi saldo, lalu sinkronkan ke rekonsiliasi.</p>
        </div>
        <div class="inline-flex p-1 rounded-2xl bg-slate-200/75 self-start sm:self-auto overflow-x-auto no-scrollbar">
          <button
            type="button"
            data-switch-view="upload"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold whitespace-nowrap transition ${
              state.view === "upload" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            + Upload PDF
          </button>
          <button
            type="button"
            data-switch-view="batches"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold whitespace-nowrap transition inline-flex items-center gap-1.5 ${
              state.view === "batches" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            <span>Riwayat Batch</span>
            <span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
              state.view === "batches" ? "bg-slate-900 text-white" : "bg-slate-300/80 text-slate-700"
            }">${batchCount}</span>
          </button>
          <button
            type="button"
            data-switch-view="rows"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold whitespace-nowrap transition ${
              state.view === "rows" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            Daftar Mutasi
          </button>
        </div>
      </div>
    `;
  }

  function renderStepProgress() {
    const steps = ["Upload PDF", "Review & Cek Saldo", "Selesai"];
    return `
      <div class="flex items-center justify-between gap-2 pb-4 border-b border-slate-100">
        <div class="flex items-center gap-2 sm:gap-3 overflow-x-auto no-scrollbar">
          ${steps
            .map((label, idx) => {
              const n = idx + 1;
              const active = state.step === n;
              const done = state.step > n;
              const dotCls = active
                ? "bg-slate-900 text-white"
                : done
                  ? "bg-emerald-600 text-white"
                  : "bg-slate-100 text-slate-400";
              const textCls = active
                ? "text-slate-900 font-bold"
                : done
                  ? "text-emerald-700 font-semibold"
                  : "text-slate-400 font-medium";
              return `
                <div class="flex items-center gap-2 shrink-0">
                  <span class="w-6 h-6 rounded-full text-[11px] font-bold flex items-center justify-center ${dotCls}">
                    ${done ? "✓" : n}
                  </span>
                  <span class="text-xs ${textCls}">${label}</span>
                  ${idx < steps.length - 1 ? `<span class="w-5 h-px bg-slate-200 hidden sm:block"></span>` : ""}
                </div>
              `;
            })
            .join("")}
        </div>
        ${
          state.step > 1
            ? `<button type="button" data-reset-wizard class="shrink-0 text-xs font-semibold text-slate-500 hover:text-slate-900 px-2.5 py-1 rounded-lg hover:bg-slate-100 transition">Reset</button>`
            : ""
        }
      </div>
    `;
  }

  function renderUploadStep1() {
    const selectedAcc = state.metadata.find(
      (a) => String(a.id) === String(state.selectedRekeningId)
    );
    const hintText = selectedAcc
      ? `${selectedAcc.bank_lembaga} · No. Rek ${selectedAcc.no_rekening} (${selectedAcc.atas_nama})`
      : "Mode Auto: sistem mendeteksi nomor rekening dari isi PDF dan mencocokkannya ke rekening perusahaan.";

    const options = [
      { id: "AUTO", title: "Auto Deteksi", sub: "Cocokkan dari isi PDF" },
      ...state.metadata.map((acc) => ({
        id: String(acc.id),
        title: acc.kode_akun,
        sub: acc.no_rekening,
      })),
    ];

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
        ${renderStepProgress()}

        <!-- Segmented Rekening Selector -->
        <div class="space-y-2.5">
          <div class="flex items-center justify-between gap-2 px-1">
            <label class="text-xs font-bold text-slate-700">Target Rekening Perusahaan</label>
            <span class="px-2.5 py-0.5 rounded-full bg-slate-100 text-[11px] font-semibold text-slate-600">
              Non-tunai saja (Kas dikecualikan)
            </span>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 p-1 rounded-2xl bg-slate-100">
            ${options
              .map((opt) => {
                const active = String(state.selectedRekeningId) === opt.id;
                return `
                  <button
                    type="button"
                    data-select-rekening="${esc(opt.id)}"
                    class="px-3 py-2 rounded-xl text-left transition ${
                      active ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                    }"
                  >
                    <p class="text-xs font-bold truncate">${esc(opt.title)}</p>
                    <p class="font-mono text-[10px] truncate ${active ? "text-slate-500" : "text-slate-400"}">${esc(opt.sub)}</p>
                  </button>
                `;
              })
              .join("")}
          </div>
          <p class="text-xs text-slate-500 px-1">${esc(hintText)}</p>
        </div>

        <!-- PDF Upload Dropzone -->
        <div
          data-pdf-dropzone
          class="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 flex flex-col gap-3 transition"
        >
          <div class="flex items-start justify-between gap-2">
            <div>
              <div class="flex items-center gap-1.5">
                <span class="px-1.5 py-0.5 rounded-md bg-slate-900 text-white text-[10px] font-bold">PDF</span>
                <h3 class="text-xs font-bold text-slate-900">Dokumen Rekening Koran Bank</h3>
              </div>
              <p class="text-[11px] text-slate-500 mt-1">
                PDF teks (BRI IBBIZ) diparsing deterministik 0 token AI · PDF vektor/scan (BNI Wondr, Bank Jago, BRI Ops) via Vision AI.
              </p>
            </div>
            <span class="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800">Wajib</span>
          </div>

          ${
            state.selectedFile
              ? `<div class="rounded-xl bg-white border border-slate-200 p-3.5 flex items-center justify-between gap-3">
                  <div class="flex items-center gap-3 min-w-0">
                    <div class="w-10 h-10 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center shrink-0">
                      ${ICON_PDF}
                    </div>
                    <div class="min-w-0">
                      <p class="text-xs font-bold text-slate-900 truncate">${esc(state.selectedFile.name)}</p>
                      <p class="text-[11px] text-slate-500 font-mono">${(state.selectedFile.size / 1024).toFixed(1)} KB · Siap diekstrak</p>
                    </div>
                  </div>
                  <div class="flex items-center gap-2 shrink-0">
                    <label class="h-8 px-3 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 inline-flex items-center cursor-pointer transition">
                      Ganti
                      <input type="file" accept="application/pdf,.pdf" data-pdf-input class="hidden" />
                    </label>
                    <button
                      type="button"
                      data-clear-pdf
                      aria-label="Hapus file PDF"
                      class="w-8 h-8 rounded-lg border border-rose-200 text-rose-600 hover:bg-rose-50 text-xs font-bold inline-flex items-center justify-center transition"
                    >✕</button>
                  </div>
                </div>`
              : `<label class="rounded-xl border-2 border-dashed border-slate-300 hover:border-blue-500 bg-white px-4 py-8 flex flex-col items-center justify-center text-center cursor-pointer transition group">
                  <div class="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-2.5 group-hover:scale-105 transition">
                    ${ICON_UPLOAD}
                  </div>
                  <span class="text-xs font-semibold text-slate-800">Pilih atau tarik file PDF rekening koran ke sini</span>
                  <span class="text-[11px] text-slate-400 mt-0.5">Format .pdf · 1 dokumen per batch upload</span>
                  <input type="file" accept="application/pdf,.pdf" data-pdf-input class="hidden" />
                </label>`
          }
        </div>

        ${
          state.extractError
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs font-semibold text-rose-800">${esc(state.extractError)}</div>`
            : ""
        }

        <div class="flex items-center justify-end pt-1">
          <button
            type="button"
            data-preview-btn
            ${!state.selectedFile || state.isExtracting ? "disabled" : ""}
            class="h-11 px-6 rounded-2xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs inline-flex items-center gap-2 transition"
          >
            ${
              state.isExtracting
                ? `<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path></svg><span>Mengekstrak PDF...</span>`
                : `<span>Proses &amp; Cek Saldo →</span>`
            }
          </button>
        </div>
      </div>
    `;
  }

  function renderUploadStep2() {
    const prev = state.previewData;
    if (!prev) return "";
    const summary = computeClientSummary(
      state.editableRows,
      prev.summary?.printed_saldo_awal ?? null,
      prev.summary?.printed_saldo_akhir ?? null
    );
    const dup = prev.duplicate_batch;
    const baseWarnings = (prev.warnings || []).filter(
      (w) => !String(w).startsWith("PERINGATAN KERAS:")
    );

    const searchQ = state.previewSearch.trim().toLowerCase();
    const visibleRows = state.editableRows
      .map((row, idx) => ({ row, idx }))
      .filter(({ row, idx }) => {
        if (state.showOnlyMismatch && !summary.mismatchIndices.has(idx)) return false;
        if (!searchQ) return true;
        return `${row.tanggal} ${row.waktu} ${row.uraian} ${row.tipe} ${row.nominal}`
          .toLowerCase()
          .includes(searchQ);
      });

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
        ${renderStepProgress()}

        ${
          !summary.balance_valid
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 p-4 space-y-1">
                <p class="text-xs font-bold text-rose-900">
                  PERINGATAN KERAS: ${
                    summary.printed_mismatch
                      ? esc(summary.printed_mismatch)
                      : `Saldo awal + CR - DB tidak cocok dengan saldo akhir (Selisih ${formatRp(summary.selisih_saldo)})`
                  }
                </p>
                <p class="text-xs text-rose-800">
                  Periksa baris yang ditandai merah di bawah ini, lalu klik Edit atau + Tambah Baris sebelum menyimpan.
                </p>
              </div>`
            : ""
        }

        ${
          baseWarnings.length
            ? `<div class="rounded-2xl bg-amber-50 border border-amber-200 p-4 space-y-1">
                <p class="text-xs font-bold text-amber-900">Perhatian:</p>
                <ul class="list-disc pl-4 text-xs text-amber-800 space-y-0.5">${baseWarnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
              </div>`
            : ""
        }

        <!-- Header File & Ringkasan Saldo -->
        <div class="rounded-2xl bg-slate-50 border border-slate-200/90 p-4 space-y-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="px-2.5 py-0.5 rounded-lg bg-slate-900 text-white text-xs font-bold">${esc(prev.rekening.kode_akun)}</span>
                <span class="text-xs sm:text-sm font-bold text-slate-900 truncate">${esc(prev.nama_file)}</span>
                <span class="px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 text-[11px] font-semibold">${esc(prev.metode_ekstraksi)}</span>
              </div>
              <p class="text-[11px] text-slate-500 mt-1">
                No. Rek ${esc(prev.detected_no_rekening || prev.rekening.no_rekening)} · Periode ${esc(summary.periode_mulai)} s.d. ${esc(summary.periode_selesai)} · ${state.editableRows.length} baris
              </p>
            </div>

            <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold ${
              summary.balance_valid ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"
            }">
              <span class="w-2 h-2 rounded-full ${summary.balance_valid ? "bg-emerald-600" : "bg-rose-600"}"></span>
              ${
                summary.balance_valid
                  ? "Saldo Konsisten (Selisih Rp0)"
                  : summary.printed_mismatch
                    ? esc(summary.printed_mismatch)
                    : `Selisih ${formatRp(summary.selisih_saldo)}`
              }
            </span>
          </div>

          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2.5 pt-3 border-t border-slate-200/80">
            <div class="rounded-xl bg-white border border-slate-200/70 p-3">
              <p class="text-[11px] font-semibold text-slate-500">Saldo Awal Periode</p>
              <p class="font-mono text-sm font-extrabold text-slate-900 tabular-nums mt-0.5">${formatRp(summary.saldo_awal_periode)}</p>
            </div>
            <div class="rounded-xl bg-white border border-emerald-200/80 p-3">
              <p class="text-[11px] font-semibold text-emerald-700">Total Masuk (CR)</p>
              <p class="font-mono text-sm font-extrabold text-emerald-700 tabular-nums mt-0.5">+${formatRp(summary.total_cr)}</p>
            </div>
            <div class="rounded-xl bg-white border border-rose-200/80 p-3">
              <p class="text-[11px] font-semibold text-rose-700">Total Keluar (DB)</p>
              <p class="font-mono text-sm font-extrabold text-rose-700 tabular-nums mt-0.5">-${formatRp(summary.total_db)}</p>
            </div>
            <div class="rounded-xl bg-slate-900 text-white p-3">
              <p class="text-[11px] font-semibold text-slate-300">Saldo Akhir Periode</p>
              <p class="font-mono text-sm font-extrabold tabular-nums mt-0.5">${formatRp(summary.saldo_akhir_periode)}</p>
            </div>
          </div>
        </div>

        ${
          dup
            ? `<label class="flex items-start gap-2.5 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 cursor-pointer">
                <input type="checkbox" data-replace-toggle ${state.replaceExisting ? "checked" : ""} class="mt-0.5 rounded border-amber-400" />
                <span class="text-xs font-semibold text-amber-950">
                  File PDF ini sudah ada di Batch #${esc(dup.id)}. Centang untuk menimpa (replace) batch lama dan menghitung ulang rekonsiliasi.
                </span>
              </label>`
            : ""
        }

        <!-- Toolbar Tabel Preview -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div class="relative flex-1 max-w-sm">
            <span class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input
              type="text"
              data-preview-search
              value="${esc(state.previewSearch)}"
              placeholder="Cari uraian, tanggal, atau nominal di preview..."
              class="w-full h-9 pl-9 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
            />
          </div>
          <div class="flex items-center gap-2">
            ${
              summary.mismatchIndices.size > 0
                ? `<button type="button" data-toggle-mismatch class="h-9 px-3 rounded-xl border text-xs font-semibold transition ${
                    state.showOnlyMismatch
                      ? "bg-rose-600 border-rose-600 text-white"
                      : "bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100"
                  }">
                    Selisih (${summary.mismatchIndices.size})
                  </button>`
                : ""
            }
            <button type="button" data-add-preview-row class="h-9 px-3.5 rounded-xl border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-800 transition">
              + Tambah Baris
            </button>
          </div>
        </div>

        <!-- Preview Table (Desktop) -->
        <div class="hidden md:block border border-slate-200 rounded-2xl overflow-hidden">
          <div class="overflow-x-auto max-h-[430px]">
            <table class="w-full text-left border-collapse text-xs">
              <thead class="sticky top-0 z-10 bg-slate-50/95 backdrop-blur-xs border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                <tr>
                  <th class="py-3 pl-4 pr-2">#</th>
                  <th class="py-3 px-2.5">Tanggal &amp; Waktu</th>
                  <th class="py-3 px-2.5">Uraian Transaksi</th>
                  <th class="py-3 px-2.5">Tipe</th>
                  <th class="py-3 px-2.5 text-right">Nominal</th>
                  <th class="py-3 px-2.5 text-right">Saldo</th>
                  <th class="py-3 pl-2.5 pr-4 text-right">Aksi</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-100">
                ${
                  visibleRows.length === 0
                    ? `<tr><td colspan="7" class="py-10 text-center text-xs text-slate-400">Tidak ada baris preview yang cocok.</td></tr>`
                    : visibleRows
                        .map(({ row, idx }) => {
                          const isCr = row.tipe === "CR";
                          const isMismatch = summary.mismatchIndices.has(idx);
                          return `
                            <tr class="${
                              isMismatch
                                ? "bg-rose-50/60"
                                : row.already_exists
                                  ? "bg-amber-50/40"
                                  : "hover:bg-slate-50/70"
                            } transition">
                              <td class="py-3 pl-4 pr-2 font-mono text-[11px] text-slate-400 align-top">${idx + 1}</td>
                              <td class="py-3 px-2.5 font-mono whitespace-nowrap align-top">
                                <p class="font-semibold text-slate-900">${esc(row.tanggal)}</p>
                                <p class="text-[11px] text-slate-400">${esc(row.waktu)}</p>
                              </td>
                              <td class="py-3 px-2.5 max-w-[300px] align-top">
                                <p class="text-slate-900 font-medium leading-snug">${esc(row.uraian)}</p>
                                <div class="flex flex-wrap gap-1.5 mt-1">
                                  ${
                                    row.already_exists
                                      ? `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">Sudah Ada (Akan Dilewati)</span>`
                                      : ""
                                  }
                                  ${
                                    isMismatch
                                      ? `<span class="px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-[10px] font-bold">Saldo berjalan tidak sesuai</span>`
                                      : ""
                                  }
                                </div>
                              </td>
                              <td class="py-3 px-2.5 whitespace-nowrap align-top">
                                <span class="px-2 py-0.5 rounded-md font-mono text-[10px] font-bold ${
                                  isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                                }">${esc(row.tipe)}</span>
                              </td>
                              <td class="py-3 px-2.5 text-right font-mono font-bold tabular-nums whitespace-nowrap align-top ${
                                isCr ? "text-emerald-700" : "text-slate-900"
                              }">${isCr ? "+" : "-"}${formatRp(row.nominal)}</td>
                              <td class="py-3 px-2.5 text-right font-mono tabular-nums whitespace-nowrap align-top text-slate-600">${formatRp(row.saldo)}</td>
                              <td class="py-3 pl-2.5 pr-4 text-right whitespace-nowrap align-top">
                                <div class="inline-flex items-center gap-1">
                                  <button type="button" data-edit-preview-row="${idx}" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold inline-flex items-center gap-1 transition">
                                    ${ICON_EDIT}<span>Edit</span>
                                  </button>
                                  <button type="button" data-remove-row="${idx}" aria-label="Hapus baris" class="h-8 w-8 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-600 inline-flex items-center justify-center transition">
                                    ${ICON_TRASH}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          `;
                        })
                        .join("")
                }
              </tbody>
            </table>
          </div>
        </div>

        <!-- Preview Cards (Mobile) -->
        <div class="md:hidden border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden">
          ${
            visibleRows.length === 0
              ? `<div class="py-10 px-4 text-center text-xs text-slate-400">Tidak ada baris preview yang cocok.</div>`
              : visibleRows
                  .map(({ row, idx }) => {
                    const isCr = row.tipe === "CR";
                    const isMismatch = summary.mismatchIndices.has(idx);
                    return `
                      <article class="p-3.5 space-y-2 ${isMismatch ? "bg-rose-50/50" : row.already_exists ? "bg-amber-50/40" : "bg-white"}">
                        <div class="flex items-start justify-between gap-2">
                          <div class="min-w-0">
                            <div class="flex items-center gap-1.5 text-[11px]">
                              <span class="font-mono text-slate-400">#${idx + 1}</span>
                              <span class="font-mono font-semibold text-slate-700">${esc(row.tanggal)} ${esc(row.waktu)}</span>
                              <span class="px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}">${esc(row.tipe)}</span>
                            </div>
                            <p class="text-xs font-semibold text-slate-900 mt-1">${esc(row.uraian)}</p>
                          </div>
                          <div class="text-right shrink-0">
                            <p class="font-mono text-xs font-extrabold tabular-nums ${isCr ? "text-emerald-700" : "text-slate-900"}">${isCr ? "+" : "-"}${formatRp(row.nominal)}</p>
                            <p class="font-mono text-[10px] text-slate-400">Saldo ${formatRp(row.saldo)}</p>
                          </div>
                        </div>
                        <div class="flex items-center justify-between gap-2 pt-1">
                          <div class="flex flex-wrap gap-1">
                            ${row.already_exists ? `<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">Duplikat</span>` : ""}
                            ${isMismatch ? `<span class="px-2 py-0.5 rounded-full bg-rose-100 text-rose-700 text-[10px] font-bold">Selisih</span>` : ""}
                          </div>
                          <div class="flex items-center gap-1.5">
                            <button type="button" data-edit-preview-row="${idx}" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white text-[11px] font-semibold text-slate-700 inline-flex items-center gap-1">${ICON_EDIT}<span>Edit</span></button>
                            <button type="button" data-remove-row="${idx}" class="h-8 w-8 rounded-lg border border-rose-200 bg-white text-rose-600 inline-flex items-center justify-center">${ICON_TRASH}</button>
                          </div>
                        </div>
                      </article>
                    `;
                  })
                  .join("")
          }
        </div>

        ${
          state.saveError
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs font-semibold text-rose-700">${esc(state.saveError)}</div>`
            : ""
        }

        <div class="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-100">
          <button type="button" data-back-step1 class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition">
            ← Ganti PDF
          </button>
          <button
            type="button"
            data-save-mutasi-btn
            ${state.isSaving || !state.editableRows.length ? "disabled" : ""}
            class="h-10 px-6 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs transition"
          >
            ${state.isSaving ? "Menyimpan..." : "Simpan Batch Mutasi"}
          </button>
        </div>
      </div>
    `;
  }

  function renderUploadStep3() {
    const res = state.saveResult;
    if (!res) return "";
    const matched = res.reconciliation?.matched_transactions || 0;
    const unmatched = res.reconciliation?.unmatched_mutasi || 0;

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-6 sm:p-8 shadow-2xs space-y-6">
        ${renderStepProgress()}

        <div class="max-w-md mx-auto text-center space-y-4 py-2">
          <div class="w-14 h-14 rounded-2xl bg-emerald-50 text-emerald-600 mx-auto flex items-center justify-center">
            <svg class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="m5 13 4 4L19 7" />
            </svg>
          </div>
          <div class="space-y-1">
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 font-mono">
              Batch #${esc(res.batch_id)} · ${esc(res.rekening)}
            </span>
            <h3 class="text-lg font-bold text-slate-900">${esc(res.message)}</h3>
            <p class="text-xs text-slate-500">
              ${unmatched} baris mutasi masuk status Belum Tercatat untuk ditinjau di Rekonsiliasi.
            </p>
          </div>

          <div class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold ${
            matched > 0 ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-700"
          }">
            <span>Auto-Rekonsiliasi: ${matched} transaksi struk cocok otomatis</span>
          </div>

          <div class="flex flex-wrap items-center justify-center gap-2 pt-2">
            <button type="button" data-reset-wizard class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition">
              + Upload PDF Lain
            </button>
            <button type="button" data-switch-view="rows" class="h-10 px-4 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition">
              Lihat Daftar Mutasi
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function renderBatchesView() {
    const query = state.batchSearch.trim().toLowerCase();
    const allItems = state.batches || [];
    const items = allItems.filter((b) => {
      if (!query) return true;
      return `${b.id} ${b.nama_file} ${b.rekening} ${b.no_rekening} ${b.metode_ekstraksi} ${b.uploaded_by || ""}`
        .toLowerCase()
        .includes(query);
    });

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
        <div class="p-4 sm:p-5 border-b border-slate-100 space-y-3.5">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p class="text-xs font-bold text-slate-900">Riwayat Batch Upload PDF (${items.length})</p>
              <p class="text-[11px] text-slate-500">Menghapus batch akan otomatis menghitung ulang status rekonsiliasi transaksi struk terkait.</p>
            </div>
            <button type="button" data-refresh-batches class="h-8 px-3 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1.5 transition">
              ${ICON_REFRESH}<span>Refresh</span>
            </button>
          </div>

          <div class="relative">
            <span class="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
            <input
              type="text"
              data-batch-search
              value="${esc(state.batchSearch)}"
              placeholder="Cari nama file PDF, rekening, metode ekstraksi, atau #Batch..."
              class="w-full h-10 pl-10 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
            />
          </div>

          ${
            state.listNotice
              ? `<div class="rounded-xl bg-emerald-50 border border-emerald-200 px-3.5 py-2 text-xs font-semibold text-emerald-800 flex items-center justify-between">
                  <span>${esc(state.listNotice)}</span>
                  <button type="button" data-dismiss-notice class="text-emerald-600 hover:text-emerald-900 font-bold">✕</button>
                </div>`
              : ""
          }
        </div>

        ${
          state.listError
            ? `<div class="p-5 text-xs font-semibold text-rose-600">${esc(state.listError)}</div>`
            : items.length === 0
              ? `<div class="py-12 px-4 text-center space-y-1">
                  <p class="text-sm font-semibold text-slate-700">Belum ada batch mutasi PDF</p>
                  <p class="text-xs text-slate-400">Upload file rekening koran di tab + Upload PDF untuk memulai.</p>
                </div>`
              : `
                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                  <table class="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        <th class="py-3 pl-5 pr-3">File Batch</th>
                        <th class="py-3 px-3">Rekening</th>
                        <th class="py-3 px-3">Periode &amp; Metode</th>
                        <th class="py-3 px-3 text-right">Saldo Awal → Akhir</th>
                        <th class="py-3 px-3 text-right">Baris</th>
                        <th class="py-3 pl-3 pr-5 text-right">Aksi</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      ${items
                        .map(
                          (b) => `
                            <tr class="hover:bg-slate-50/70 transition">
                              <td class="py-3.5 pl-5 pr-3 align-top">
                                <p class="font-bold text-slate-900">#${b.id} · ${esc(b.nama_file)}</p>
                                <p class="text-[11px] text-slate-400 mt-0.5">${esc(b.uploaded_by || "-")} · ${esc(b.created_at)}</p>
                              </td>
                              <td class="py-3.5 px-3 whitespace-nowrap align-top">
                                <span class="px-2 py-0.5 rounded-md bg-slate-100 text-slate-800 font-bold">${esc(b.rekening)}</span>
                                <p class="font-mono text-[11px] text-slate-400 mt-0.5">${esc(b.no_rekening)}</p>
                              </td>
                              <td class="py-3.5 px-3 whitespace-nowrap align-top">
                                <p class="font-mono text-slate-800">${esc(b.periode_mulai)} s.d. ${esc(b.periode_selesai)}</p>
                                <p class="text-[11px] text-blue-700 font-semibold mt-0.5">${esc(b.metode_ekstraksi)}</p>
                              </td>
                              <td class="py-3.5 px-3 text-right font-mono whitespace-nowrap align-top">
                                <p class="text-slate-500">${formatRp(b.saldo_awal_periode)}</p>
                                <p class="font-bold text-slate-900">→ ${formatRp(b.saldo_akhir_periode)}</p>
                              </td>
                              <td class="py-3.5 px-3 text-right font-mono font-bold text-slate-900 align-top">${b.jumlah_baris}</td>
                              <td class="py-3.5 pl-3 pr-5 text-right whitespace-nowrap align-top">
                                <div class="inline-flex items-center gap-1.5">
                                  <button type="button" data-view-batch-rows="${b.id}" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-[11px] font-semibold text-slate-700 transition">Lihat Baris</button>
                                  <button type="button" data-delete-batch="${b.id}" data-batch-name="${esc(b.nama_file)}" aria-label="Hapus batch" class="h-8 w-8 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-600 inline-flex items-center justify-center transition">${ICON_TRASH}</button>
                                </div>
                              </td>
                            </tr>
                          `
                        )
                        .join("")}
                    </tbody>
                  </table>
                </div>

                <!-- Mobile Cards -->
                <div class="md:hidden divide-y divide-slate-100">
                  ${items
                    .map(
                      (b) => `
                        <article class="p-4 space-y-2.5">
                          <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                              <div class="flex items-center gap-1.5">
                                <span class="font-mono text-[11px] text-slate-400">#${b.id}</span>
                                <span class="px-2 py-0.5 rounded bg-slate-100 text-slate-800 text-[10px] font-bold">${esc(b.rekening)}</span>
                                <span class="text-[10px] font-semibold text-blue-700">${esc(b.metode_ekstraksi)}</span>
                              </div>
                              <p class="text-xs font-bold text-slate-900 truncate mt-1">${esc(b.nama_file)}</p>
                              <p class="font-mono text-[11px] text-slate-500">${esc(b.periode_mulai)} s.d. ${esc(b.periode_selesai)} · ${b.jumlah_baris} baris</p>
                            </div>
                          </div>
                          <div class="flex items-center justify-between gap-2 pt-1">
                            <span class="font-mono text-[11px] text-slate-700 font-semibold">${formatRp(b.saldo_awal_periode)} → ${formatRp(b.saldo_akhir_periode)}</span>
                            <div class="flex items-center gap-1.5">
                              <button type="button" data-view-batch-rows="${b.id}" class="h-8 px-3 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700">Lihat Baris</button>
                              <button type="button" data-delete-batch="${b.id}" data-batch-name="${esc(b.nama_file)}" class="h-8 w-8 rounded-lg border border-rose-200 text-rose-600 inline-flex items-center justify-center">${ICON_TRASH}</button>
                            </div>
                          </div>
                        </article>
                      `
                    )
                    .join("")}
                </div>
              `
        }
      </div>
    `;
  }

  function renderRowsView() {
    const items = state.rows || [];
    const totalCr = items.reduce((s, r) => s + (r.tipe === "CR" ? Number(r.nominal || 0) : 0), 0);
    const totalDb = items.reduce((s, r) => s + (r.tipe === "DB" ? Number(r.nominal || 0) : 0), 0);

    const statusTabs = [
      { id: "", label: "Semua" },
      { id: "BELUM_TERCATAT", label: "Belum Tercatat" },
      { id: "SESUAI", label: "Sesuai Struk" },
      { id: "SELISIH_KODE_UNIK_ADMIN", label: "Selisih Admin" },
      { id: "PINDAH_BUKU", label: "Pindah Buku" },
      { id: "BELUM_REKON", label: "Belum Rekon" },
    ];

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
        <!-- Toolbar ala Input Struk -->
        <div class="p-4 sm:p-5 border-b border-slate-100 space-y-3.5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex items-center gap-2 overflow-x-auto no-scrollbar">
              ${statusTabs
                .map((f) => {
                  const active = state.rowFilters.status_rekonsiliasi === f.id;
                  return `<button type="button" data-status-pill="${f.id}" class="shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold transition ${
                    active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200/70"
                  }">${esc(f.label)}</button>`;
                })
                .join("")}
            </div>
            <div class="flex items-center gap-3 text-xs shrink-0">
              <span class="text-slate-500">
                CR <strong class="font-mono text-emerald-700 tabular-nums">+${formatRp(totalCr)}</strong> ·
                DB <strong class="font-mono text-slate-900 tabular-nums">-${formatRp(totalDb)}</strong>
              </span>
              <button type="button" data-refresh-rows class="h-8 px-3 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1.5 transition">
                ${ICON_REFRESH}<span>Refresh</span>
              </button>
            </div>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-2.5">
            <div class="relative lg:col-span-2">
              <span class="absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none">${ICON_SEARCH}</span>
              <input
                type="text"
                data-row-search
                value="${esc(state.rowFilters.search)}"
                placeholder="Cari uraian mutasi..."
                class="w-full h-10 pl-10 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
              />
            </div>
            <select data-row-filter="rekening_id" class="${INPUT_CLS}">
              <option value="">Semua Rekening</option>
              ${state.metadata
                .map(
                  (acc) =>
                    `<option value="${acc.id}" ${String(state.rowFilters.rekening_id) === String(acc.id) ? "selected" : ""}>${esc(acc.kode_akun)}</option>`
                )
                .join("")}
            </select>
            <select data-row-filter="tipe" class="${INPUT_CLS}">
              <option value="">Semua Tipe (CR/DB)</option>
              <option value="CR" ${state.rowFilters.tipe === "CR" ? "selected" : ""}>CR (Masuk)</option>
              <option value="DB" ${state.rowFilters.tipe === "DB" ? "selected" : ""}>DB (Keluar)</option>
            </select>
            <input type="date" data-row-filter="tanggal_mulai" value="${esc(state.rowFilters.tanggal_mulai)}" title="Dari Tanggal" class="${INPUT_CLS} font-mono" />
            <input type="date" data-row-filter="tanggal_selesai" value="${esc(state.rowFilters.tanggal_selesai)}" title="Sampai Tanggal" class="${INPUT_CLS} font-mono" />
          </div>

          ${
            state.rowFilters.batch_id
              ? `<div class="flex items-center gap-2 text-xs">
                  <span class="px-2.5 py-1 rounded-full bg-blue-50 text-blue-800 font-semibold">Filter Batch #${esc(state.rowFilters.batch_id)}</span>
                  <button type="button" data-clear-batch-filter class="text-slate-500 hover:text-slate-900 font-semibold">Reset Filter Batch</button>
                </div>`
              : ""
          }
        </div>

        ${
          state.listError
            ? `<div class="p-5 text-xs font-semibold text-rose-600">${esc(state.listError)}</div>`
            : items.length === 0
              ? `<div class="py-12 px-4 text-center space-y-1">
                  <p class="text-sm font-semibold text-slate-700">Tidak ada baris mutasi ditemukan</p>
                  <p class="text-xs text-slate-400">Ubah filter rekening/periode atau upload PDF mutasi baru.</p>
                </div>`
              : `
                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                  <table class="w-full text-left border-collapse text-xs">
                    <thead>
                      <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        <th class="py-3 pl-5 pr-3">Tanggal</th>
                        <th class="py-3 px-3">Rekening</th>
                        <th class="py-3 px-3">Uraian Bank</th>
                        <th class="py-3 px-3">Tipe</th>
                        <th class="py-3 px-3 text-right">Nominal</th>
                        <th class="py-3 px-3 text-right">Saldo</th>
                        <th class="py-3 pl-3 pr-5">Status Rekon</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      ${items
                        .map((r) => {
                          const badge = STATUS_BADGE[r.status_rekonsiliasi] || STATUS_BADGE.BELUM_REKON;
                          const isCr = r.tipe === "CR";
                          return `
                            <tr class="hover:bg-slate-50/70 transition">
                              <td class="py-3.5 pl-5 pr-3 font-mono whitespace-nowrap align-top">
                                <p class="font-semibold text-slate-900">${esc(r.tanggal)}</p>
                                <p class="text-[11px] text-slate-400">${esc(r.waktu)} · Batch #${r.batch_id}</p>
                              </td>
                              <td class="py-3.5 px-3 whitespace-nowrap align-top">
                                <p class="font-semibold text-slate-800">${esc(r.rekening)}</p>
                                <p class="font-mono text-[10px] text-slate-400">${esc(r.no_rekening)}</p>
                              </td>
                              <td class="py-3.5 px-3 max-w-[320px] align-top">
                                <p class="text-slate-900 font-medium leading-snug">${esc(r.uraian)}</p>
                                ${
                                  r.penyebab_selisih
                                    ? `<p class="text-[10px] font-semibold text-amber-700 mt-1">${esc(r.penyebab_selisih)}</p>`
                                    : ""
                                }
                              </td>
                              <td class="py-3.5 px-3 whitespace-nowrap align-top">
                                <span class="px-2 py-0.5 rounded-md font-mono text-[10px] font-bold ${
                                  isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                                }">${esc(r.tipe)}</span>
                              </td>
                              <td class="py-3.5 px-3 text-right font-mono text-sm font-extrabold tabular-nums whitespace-nowrap align-top ${
                                isCr ? "text-emerald-700" : "text-slate-900"
                              }">${isCr ? "+" : "-"}${formatRp(r.nominal)}</td>
                              <td class="py-3.5 px-3 text-right font-mono tabular-nums whitespace-nowrap align-top text-slate-600">${formatRp(r.saldo)}</td>
                              <td class="py-3.5 pl-3 pr-5 whitespace-nowrap align-top">
                                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
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
                    .map((r) => {
                      const badge = STATUS_BADGE[r.status_rekonsiliasi] || STATUS_BADGE.BELUM_REKON;
                      const isCr = r.tipe === "CR";
                      return `
                        <article class="p-4 space-y-2">
                          <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                              <div class="flex items-center gap-1.5">
                                <span class="font-mono text-[11px] font-semibold text-slate-600">${esc(r.tanggal)}</span>
                                <span class="px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 text-[10px] font-bold">${esc(r.rekening)}</span>
                                <span class="px-1.5 py-0.5 rounded font-mono text-[10px] font-bold ${isCr ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}">${esc(r.tipe)}</span>
                              </div>
                              <p class="text-xs font-semibold text-slate-900 mt-1">${esc(r.uraian)}</p>
                              ${r.penyebab_selisih ? `<p class="text-[10px] font-semibold text-amber-700 mt-0.5">${esc(r.penyebab_selisih)}</p>` : ""}
                            </div>
                            <div class="text-right shrink-0">
                              <p class="font-mono text-sm font-extrabold tabular-nums ${isCr ? "text-emerald-700" : "text-slate-900"}">${isCr ? "+" : "-"}${formatRp(r.nominal)}</p>
                              <p class="font-mono text-[10px] text-slate-400">Saldo ${formatRp(r.saldo)}</p>
                            </div>
                          </div>
                          <div class="flex items-center justify-between pt-1">
                            <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${badge.cls}">${esc(badge.label)}</span>
                            <span class="font-mono text-[10px] text-slate-400">${esc(r.waktu)} · Batch #${r.batch_id}</span>
                          </div>
                        </article>
                      `;
                    })
                    .join("")}
                </div>
              `
        }
      </div>
    `;
  }

  function bindEvents(root) {
    root.querySelectorAll("[data-switch-view]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        state.view = btn.dataset.switchView;
        state.listNotice = "";
        if (state.view === "batches") await loadBatches();
        if (state.view === "rows") await loadRows();
        render();
      });
    });

    root.querySelectorAll("[data-select-rekening]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.selectedRekeningId = btn.dataset.selectRekening;
        render();
      });
    });

    root.querySelector("[data-pdf-input]")?.addEventListener("change", (e) => {
      const f = e.target.files?.[0];
      if (f) setSelectedPdf(f);
    });

    root.querySelector("[data-clear-pdf]")?.addEventListener("click", () => {
      state.selectedFile = null;
      state.extractError = "";
      render();
    });

    const dropzone = root.querySelector("[data-pdf-dropzone]");
    if (dropzone) {
      dropzone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropzone.classList.add("border-blue-500", "bg-blue-50/40");
      });
      dropzone.addEventListener("dragleave", () => {
        dropzone.classList.remove("border-blue-500", "bg-blue-50/40");
      });
      dropzone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropzone.classList.remove("border-blue-500", "bg-blue-50/40");
        const f = e.dataTransfer?.files?.[0];
        if (f) setSelectedPdf(f);
      });
    }

    root.querySelector("[data-preview-btn]")?.addEventListener("click", handlePreview);
    root.querySelector("[data-reset-wizard]")?.addEventListener("click", resetWizard);
    root.querySelector("[data-back-step1]")?.addEventListener("click", () => {
      state.step = 1;
      state.saveError = "";
      render();
    });
    root.querySelector("[data-save-mutasi-btn]")?.addEventListener("click", handleSave);

    root.querySelector("[data-replace-toggle]")?.addEventListener("change", (e) => {
      state.replaceExisting = Boolean(e.target.checked);
    });

    root.querySelector("[data-preview-search]")?.addEventListener("input", (e) => {
      state.previewSearch = e.target.value;
      const cursor = e.target.selectionStart;
      render();
      const next = container.querySelector("[data-preview-search]");
      if (next) {
        next.focus();
        next.setSelectionRange(cursor, cursor);
      }
    });

    root.querySelector("[data-toggle-mismatch]")?.addEventListener("click", () => {
      state.showOnlyMismatch = !state.showOnlyMismatch;
      render();
    });

    root.querySelector("[data-add-preview-row]")?.addEventListener("click", () => openRowModal(null));

    root.querySelectorAll("[data-edit-preview-row]").forEach((btn) => {
      btn.addEventListener("click", () => openRowModal(Number(btn.dataset.editPreviewRow)));
    });

    root.querySelectorAll("[data-remove-row]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const idx = Number(btn.dataset.removeRow);
        state.editableRows = state.editableRows.filter((_, i) => i !== idx);
        render();
      });
    });

    root.querySelector("[data-batch-search]")?.addEventListener("input", (e) => {
      state.batchSearch = e.target.value;
      const cursor = e.target.selectionStart;
      render();
      const next = container.querySelector("[data-batch-search]");
      if (next) {
        next.focus();
        next.setSelectionRange(cursor, cursor);
      }
    });

    root.querySelector("[data-dismiss-notice]")?.addEventListener("click", () => {
      state.listNotice = "";
      render();
    });

    root.querySelector("[data-refresh-batches]")?.addEventListener("click", async () => {
      await loadBatches();
      render();
    });

    root.querySelector("[data-refresh-rows]")?.addEventListener("click", async () => {
      await loadRows();
      render();
    });

    root.querySelectorAll("[data-view-batch-rows]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        state.rowFilters.batch_id = btn.dataset.viewBatchRows;
        state.view = "rows";
        await loadRows();
        render();
      });
    });

    root.querySelectorAll("[data-delete-batch]").forEach((btn) => {
      btn.addEventListener("click", () =>
        handleDeleteBatch(Number(btn.dataset.deleteBatch), btn.dataset.batchName || "")
      );
    });

    root.querySelectorAll("[data-status-pill]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        state.rowFilters.status_rekonsiliasi = btn.dataset.statusPill;
        await loadRows();
        render();
      });
    });

    root.querySelectorAll("[data-row-filter]").forEach((sel) => {
      sel.addEventListener("change", async (e) => {
        state.rowFilters[sel.dataset.rowFilter] = e.target.value;
        await loadRows();
        render();
      });
    });

    root.querySelector("[data-clear-batch-filter]")?.addEventListener("click", async () => {
      state.rowFilters.batch_id = "";
      await loadRows();
      render();
    });

    root.querySelector("[data-row-search]")?.addEventListener("input", (e) => {
      state.rowFilters.search = e.target.value;
      if (rowSearchTimer) clearTimeout(rowSearchTimer);
      rowSearchTimer = setTimeout(async () => {
        const activeInput = container.querySelector("[data-row-search]");
        const cursor = activeInput ? activeInput.selectionStart : e.target.value.length;
        await loadRows();
        render();
        const next = container.querySelector("[data-row-search]");
        if (next) {
          next.focus();
          next.setSelectionRange(cursor, cursor);
        }
      }, 220);
    });
  }

  function render() {
    const wrapper = document.createElement("div");
    wrapper.className = "space-y-5 view-animate";
    const mainHtml =
      state.view === "batches"
        ? renderBatchesView()
        : state.view === "rows"
          ? renderRowsView()
          : state.step === 1
            ? renderUploadStep1()
            : state.step === 2
              ? renderUploadStep2()
              : renderUploadStep3();
    wrapper.innerHTML = `${renderTopBar()}${mainHtml}`;
    container.replaceChildren(wrapper);
    bindEvents(wrapper);
  }

  await Promise.all([loadMetadata(), loadBatches()]);
  render();
}
