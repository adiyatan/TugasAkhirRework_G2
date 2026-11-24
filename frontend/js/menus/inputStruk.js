import { apiFetch } from "../api.js";
import {
  formatAiCostIdr,
  formatTokenCount,
  renderAiCostCard,
  renderAiCostRowBadge,
} from "./shared.js";

const TAB_CONFIG = {
  normal: {
    label: "Normal",
    hint: "Nota, QRIS, transfer biasa, atau tunai kas.",
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h4M7 3h10a2 2 0 0 1 2 2v16l-3-2-2 2-2-2-2 2-2-2-3 2V5a2 2 0 0 1 2-2Z"/></svg>`,
    slotA: { title: "Bukti Bayar / Terima", sub: "1+ foto bukti sah (atau nota tunai)", required: true, multiple: true },
    slotB: { title: "Rincian Item", sub: "Opsional · daftar belanja / invoice", required: false, multiple: true },
    slotC: null,
  },
  flip: {
    label: "Transfer Flip",
    hint: "1 bukti Bank → Flip + 1..N bukti Flip → Penerima.",
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4"/></svg>`,
    slotA: { title: "Bank → PT Fliptech", sub: "Wajib tepat 1 foto transfer ke Flip", required: true, multiple: false, exactOne: true },
    slotB: { title: "Flip → Penerima", sub: "Wajib 1..N foto struk penerima akhir", required: true, multiple: true },
    slotC: { title: "Nota / Resi", sub: "Opsional · lampiran pendukung", required: false, multiple: true },
  },
  slip_gaji: {
    label: "Slip Gaji",
    hint: "Slip gaji (Slot A) + bukti transfer gaji (Slot B).",
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 9V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2m2 4h10a2 2 0 0 0 2-2v-6a2 2 0 0 0-2-2H9a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2Zm7-5a2 2 0 1 1-4 0 2 2 0 0 1 4 0Z"/></svg>`,
    slotA: { title: "Slip Gaji / Rekap Fee", sub: "Wajib 1+ foto slip gaji", required: true, multiple: true },
    slotB: { title: "Bukti Transfer Gaji", sub: "Wajib 1+ bukti transfer (tanggal ikut ini)", required: true, multiple: true },
    slotC: null,
  },
  reimburse: {
    label: "Reimburse",
    hint: "Nota talangan pribadi (Slot A) + penggantian PT (Slot B).",
    icon: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 10h10a8 8 0 0 1 8 8v2M3 10l6 6m-6-6 6-6"/></svg>`,
    slotA: { title: "Nota Awal / Talangan", sub: "Wajib 1+ nota belanja / QRIS pribadi", required: true, multiple: true },
    slotB: { title: "Transfer Penggantian PT", sub: "Wajib 1+ transfer dari rekening perusahaan", required: true, multiple: true },
    slotC: null,
  },
};

const SALARY_CATEGORIES = new Set(["Biaya-Gaji Karyawan", "Pendapatan/Beban Lain"]);

const RECON_BADGE = {
  BELUM_REKON: { cls: "bg-slate-100 text-slate-700", label: "Belum Rekon" },
  MUTASI_BELUM_ADA: { cls: "bg-amber-50 text-amber-700", label: "Mutasi Belum Ada" },
  SESUAI: { cls: "bg-emerald-50 text-emerald-700", label: "Sesuai Mutasi" },
  SELISIH_KODE_UNIK_ADMIN: { cls: "bg-blue-50 text-blue-700", label: "Cocok (Selisih Admin)" },
  PINDAH_BUKU_COCOK: { cls: "bg-indigo-50 text-indigo-700", label: "Pindah Buku Cocok" },
};

const INPUT_CLS =
  "w-full h-10 px-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 disabled:bg-slate-100 disabled:text-slate-500 transition";

const ICON_LOCK = `<svg class="w-3 h-3 inline-block ml-1 -mt-0.5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><rect x="5" y="11" width="14" height="10" rx="2"/><path stroke-linecap="round" d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;
const ICON_PHOTO = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="8.5" cy="10" r="1.5"/><path stroke-linecap="round" stroke-linejoin="round" d="m21 15-4.5-4.5a1.5 1.5 0 0 0-2.1 0L7 18"/></svg>`;
const ICON_EDIT = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M16.862 3.487a2.1 2.1 0 1 1 2.97 2.97L7.5 18.79 3 20l1.21-4.5L16.862 3.487Z"/></svg>`;
const ICON_TRASH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/></svg>`;
const ICON_REFRESH = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h5M20 20v-5h-5M5.5 9A7.5 7.5 0 0 1 19 6.5M18.5 15A7.5 7.5 0 0 1 5 17.5"/></svg>`;

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatRp(amount) {
  return `Rp${Math.round(Number(amount || 0)).toLocaleString("id-ID")}`;
}

function parseErrorDetail(data, fallback) {
  if (!data) return { message: fallback, errors: [] };
  const detail = data.detail;
  if (typeof detail === "string") return { message: detail, errors: [detail] };
  if (detail && typeof detail === "object") {
    const message = detail.message || fallback;
    const errors = Array.isArray(detail.errors) ? detail.errors : [message];
    return { message, errors };
  }
  return { message: data.message || fallback, errors: [] };
}

function normalizeTime(value) {
  if (/^\d{2}:\d{2}$/.test(value)) return `${value}:00`;
  if (/^\d{2}:\d{2}:\d{2}$/.test(value)) return value;
  return "12:00:00";
}

export async function renderInputStrukMenu(container, { user, onUnauthorized }) {
  const state = {
    view: "wizard", // "wizard" | "recent"
    step: 1,
    tabType: "normal",
    isCash: false,
    showOptionalSlotC: false,
    files: { A: [], B: [], C: [] },
    previewUrls: [],
    activePhotoIdx: 0,
    metadata: null,
    extractResult: null,
    extractError: "",
    extractErrors: [],
    saveResult: null,
    saveError: "",
    needsDuplicateForce: false,
    isExtracting: false,
    isSaving: false,
    recentItems: [],
    recentSearch: "",
    recentFilter: "all",
    recentNotice: "",
    recentError: "",
  };

  function revokePreviews() {
    for (const url of state.previewUrls) URL.revokeObjectURL(url);
    state.previewUrls = [];
  }

  function previewUrl(file) {
    const url = URL.createObjectURL(file);
    state.previewUrls.push(url);
    return url;
  }

  async function loadMetadata() {
    const res = await apiFetch("/struk/metadata", {}, onUnauthorized);
    const data = await res.json();
    if (!res.ok) throw new Error(parseErrorDetail(data, "Gagal memuat metadata").message);
    state.metadata = data;
  }

  async function loadRecent() {
    try {
      const res = await apiFetch("/struk/recent?limit=30", {}, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        state.recentError = parseErrorDetail(data, "Gagal memuat riwayat").message;
        return;
      }
      state.recentItems = data.items || [];
      state.recentError = "";
    } catch (err) {
      state.recentError = err.message;
    }
  }

  function resetWizard() {
    revokePreviews();
    state.view = "wizard";
    state.step = 1;
    state.showOptionalSlotC = false;
    state.files = { A: [], B: [], C: [] };
    state.activePhotoIdx = 0;
    state.extractResult = null;
    state.extractError = "";
    state.extractErrors = [];
    state.saveResult = null;
    state.saveError = "";
    state.needsDuplicateForce = false;
    state.isExtracting = false;
    state.isSaving = false;
    render();
  }

  function addFilesToSlot(slot, fileList) {
    const cfg = TAB_CONFIG[state.tabType]?.[`slot${slot}`];
    if (!cfg) return;
    const incoming = Array.from(fileList || []).filter((f) => f.type.startsWith("image/") || f.name);
    if (!incoming.length) return;
    state.files[slot] = cfg.exactOne ? [incoming[0]] : [...state.files[slot], ...incoming];
    state.extractError = "";
    state.extractErrors = [];
    render();
  }

  function removeFileFromSlot(slot, idx) {
    state.files[slot] = state.files[slot].filter((_, i) => i !== idx);
    render();
  }

  function canExtract() {
    const cfg = TAB_CONFIG[state.tabType];
    if (!state.files.A.length) return false;
    if (cfg.slotA.exactOne && state.files.A.length !== 1) return false;
    if (cfg.slotB?.required && !state.files.B.length) return false;
    return true;
  }

  async function handleExtract() {
    if (!canExtract() || state.isExtracting) {
      const cfg = TAB_CONFIG[state.tabType];
      state.extractError = !state.files.A.length
        ? "Upload minimal 1 foto pada Slot A."
        : cfg.slotA.exactOne && state.files.A.length !== 1
          ? "Mode Transfer Flip membutuhkan tepat 1 foto di Slot A."
          : `Mode ${cfg.label} membutuhkan minimal 1 foto di Slot B.`;
      state.extractErrors = [state.extractError];
      render();
      return;
    }

    state.isExtracting = true;
    state.extractError = "";
    state.extractErrors = [];
    render();

    try {
      const formData = new FormData();
      formData.append("tab_type", state.tabType);
      formData.append("is_cash", state.tabType === "normal" && state.isCash ? "true" : "false");
      state.files.A.forEach((f) => formData.append("slot_a", f));
      state.files.B.forEach((f) => formData.append("slot_b", f));
      if (state.tabType === "flip") state.files.C.forEach((f) => formData.append("slot_c", f));

      const res = await apiFetch("/struk/extract", { method: "POST", body: formData }, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        const parsed = parseErrorDetail(data, "Ekstraksi struk gagal");
        state.extractError = parsed.message;
        state.extractErrors = parsed.errors;
        return;
      }

      state.extractResult = data;
      state.activePhotoIdx = 0;
      state.saveError = "";
      state.needsDuplicateForce = (data.warnings || []).some((w) =>
        String(w).toLowerCase().includes("duplikat")
      );
      state.step = 2;
    } catch (err) {
      state.extractError = err.message || "Gagal memproses gambar struk";
      state.extractErrors = [state.extractError];
    } finally {
      state.isExtracting = false;
      render();
    }
  }

  async function handleSave(formEl) {
    if (!state.extractResult || state.isSaving) return;
    if ((state.extractResult.errors || []).length > 0) return;

    const extracted = state.extractResult.extracted || {};
    const locked = new Set(state.extractResult.locked_fields || []);
    const getVal = (name) => (locked.has(name) ? extracted[name] : formEl.elements[name]?.value);

    const tipe = String(getVal("tipe") || "KELUAR");
    const nominalPokok = Number(getVal("nominal_pokok") || 0);
    const biayaAdmin = Number(getVal("biaya_admin_kode_unik") || 0);
    const totalMutasi = locked.has("total_mutasi")
      ? Number(extracted.total_mutasi || 0)
      : Number(getVal("total_mutasi") || nominalPokok + biayaAdmin);
    const rekTujuanRaw = getVal("rekening_tujuan_id");
    const forceEl = formEl.elements["force_save_duplicate"];

    const payload = {
      staging_id: state.extractResult.staging_id,
      tanggal_transaksi: String(getVal("tanggal_transaksi") || ""),
      waktu_transaksi: normalizeTime(String(getVal("waktu_transaksi") || "12:00:00")),
      rekening_sumber_id: Number(getVal("rekening_sumber_id")),
      rekening_tujuan_id: tipe === "PINDAH_BUKU" && rekTujuanRaw ? Number(rekTujuanRaw) : null,
      tipe,
      kategori_id: Number(getVal("kategori_id")),
      penerima_pengirim: String(getVal("penerima_pengirim") || ""),
      keterangan: String(getVal("keterangan") || ""),
      nominal_pokok: nominalPokok,
      biaya_admin_kode_unik: biayaAdmin,
      total_mutasi: totalMutasi,
      force_save_duplicate: Boolean(forceEl?.checked),
    };
    state.extractResult.extracted = { ...extracted, ...payload };

    state.isSaving = true;
    state.saveError = "";
    const btn = formEl.querySelector("[data-save-btn]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Menyimpan...";
    }

    try {
      const res = await apiFetch(
        "/struk/save",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
        onUnauthorized
      );
      const data = await res.json();
      if (!res.ok) {
        const parsed = parseErrorDetail(data, "Gagal menyimpan transaksi");
        state.saveError = parsed.message;
        if (res.status === 409 && parsed.message.toLowerCase().includes("force_save_duplicate")) {
          state.needsDuplicateForce = true;
        }
        return;
      }
      state.saveResult = data;
      state.step = 3;
      await loadRecent();
    } catch (err) {
      state.saveError = err.message || "Gagal menyimpan transaksi";
    } finally {
      state.isSaving = false;
      render();
    }
  }

  async function handleDelete(transaksiId) {
    if (!confirm(`Hapus transaksi #${transaksiId}?`)) return;
    try {
      const res = await apiFetch(`/struk/${transaksiId}`, { method: "DELETE" }, onUnauthorized);
      const data = await res.json();
      if (!res.ok) {
        alert(parseErrorDetail(data, "Gagal menghapus transaksi").message);
        return;
      }
      await loadRecent();
      render();
    } catch (err) {
      alert(err.message || "Gagal menghapus transaksi");
    }
  }

  function showLightbox(title, loadUrlOrFile) {
    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-xs flex items-center justify-center p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl modal-panel-animate">
        <div class="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between gap-3">
          <p class="text-sm font-bold text-slate-900 truncate">${esc(title)}</p>
          <button type="button" data-close-modal class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center">✕</button>
        </div>
        <div class="p-4 flex-1 overflow-auto flex items-center justify-center bg-slate-50 min-h-[260px]" data-modal-body>
          <p class="text-xs text-slate-400">Memuat gambar...</p>
        </div>
      </div>
    `;
    let createdUrl = null;
    const close = () => {
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      modal.remove();
    };
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close-modal]")) close();
    });
    document.body.appendChild(modal);

    const body = modal.querySelector("[data-modal-body]");
    if (loadUrlOrFile instanceof File) {
      createdUrl = URL.createObjectURL(loadUrlOrFile);
      body.innerHTML = `<img src="${createdUrl}" alt="${esc(title)}" class="max-h-[74vh] w-auto rounded-xl object-contain" />`;
      return;
    }

    (async () => {
      try {
        const res = await apiFetch(String(loadUrlOrFile).replace(/^\/api\/v1/, ""), {}, onUnauthorized);
        if (!res.ok) throw new Error("Gagal memuat lampiran");
        createdUrl = URL.createObjectURL(await res.blob());
        body.innerHTML = `<img src="${createdUrl}" alt="${esc(title)}" class="max-h-[74vh] w-auto rounded-xl object-contain" />`;
      } catch (err) {
        body.innerHTML = `<p class="text-xs font-semibold text-rose-600">${esc(err.message)}</p>`;
      }
    })();
  }

  function openGalleryModal(tx) {
    const files = tx.files || [];
    if (!files.length) return;
    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 bg-slate-950/75 backdrop-blur-xs flex items-center justify-center p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-3xl max-w-3xl w-full max-h-[90vh] flex flex-col overflow-hidden shadow-2xl modal-panel-animate">
        <div class="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between gap-3">
          <div class="min-w-0">
            <p class="text-sm font-bold text-slate-900 truncate">Lampiran Transaksi #${esc(tx.id)}</p>
            <p class="text-[11px] text-slate-500 truncate" data-gal-caption>${esc(files[0].orig_filename)}</p>
          </div>
          <button type="button" data-close-modal class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center">✕</button>
        </div>
        <div class="p-4 flex-1 overflow-auto flex items-center justify-center bg-slate-50 min-h-[280px]" data-gal-body>
          <p class="text-xs text-slate-400">Memuat lampiran...</p>
        </div>
        ${
          files.length > 1
            ? `<div class="px-4 py-3 border-t border-slate-100 bg-white flex items-center gap-2 overflow-x-auto no-scrollbar" data-gal-thumbs></div>`
            : ""
        }
      </div>
    `;

    const blobUrls = new Map();
    const close = () => {
      for (const u of blobUrls.values()) URL.revokeObjectURL(u);
      modal.remove();
    };
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close-modal]")) close();
    });
    document.body.appendChild(modal);

    const bodyEl = modal.querySelector("[data-gal-body]");
    const captionEl = modal.querySelector("[data-gal-caption]");
    const thumbsEl = modal.querySelector("[data-gal-thumbs]");
    let activeIdx = 0;

    async function loadFileUrl(file) {
      if (blobUrls.has(file.id)) return blobUrls.get(file.id);
      const res = await apiFetch(String(file.url).replace(/^\/api\/v1/, ""), {}, onUnauthorized);
      if (!res.ok) throw new Error("Gagal memuat file");
      const u = URL.createObjectURL(await res.blob());
      blobUrls.set(file.id, u);
      return u;
    }

    async function showIndex(idx) {
      activeIdx = idx;
      const file = files[idx];
      if (captionEl) captionEl.textContent = `Slot ${file.slot} · ${file.orig_filename}`;
      if (bodyEl) bodyEl.innerHTML = `<p class="text-xs text-slate-400">Memuat gambar...</p>`;
      try {
        const u = await loadFileUrl(file);
        if (bodyEl) {
          bodyEl.innerHTML = `<img src="${u}" alt="${esc(file.orig_filename)}" class="max-h-[68vh] w-auto rounded-xl object-contain" />`;
        }
      } catch (err) {
        if (bodyEl) bodyEl.innerHTML = `<p class="text-xs font-semibold text-rose-600">${esc(err.message)}</p>`;
      }
      if (thumbsEl) {
        thumbsEl.querySelectorAll("[data-gal-idx]").forEach((b) => {
          const isAct = Number(b.dataset.galIdx) === activeIdx;
          b.className = `px-3 py-1.5 rounded-xl text-xs font-semibold shrink-0 transition ${
            isAct ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
          }`;
        });
      }
    }

    if (thumbsEl) {
      thumbsEl.innerHTML = files
        .map(
          (f, i) =>
            `<button type="button" data-gal-idx="${i}" class="px-3 py-1.5 rounded-xl text-xs font-semibold shrink-0 bg-slate-100 text-slate-700">Slot ${esc(f.slot)} · ${esc(f.orig_filename)}</button>`
        )
        .join("");
      thumbsEl.querySelectorAll("[data-gal-idx]").forEach((btn) => {
        btn.addEventListener("click", () => showIndex(Number(btn.dataset.galIdx)));
      });
    }
    showIndex(0);
  }

  function openEditModal(tx) {
    const locked = new Set(tx.locked_fields || []);
    const accounts = state.metadata?.rekening_perusahaan || [];
    const categories = (state.metadata?.kategori_sop || []).filter((cat) =>
      tx.tab_type === "slip_gaji" ? SALARY_CATEGORIES.has(cat.nama_kategori) : true
    );
    const files = tx.files || [];
    const lockTag = (field) =>
      locked.has(field) ? `<span title="Terkunci oleh aturan ${esc(tx.tab_type)}">${ICON_LOCK}</span>` : "";

    const modal = document.createElement("div");
    modal.className = "fixed inset-0 z-50 bg-slate-950/65 backdrop-blur-xs flex items-end sm:items-center justify-center p-0 sm:p-4";
    modal.innerHTML = `
      <div class="bg-white rounded-t-3xl sm:rounded-3xl max-w-4xl w-full max-h-[92vh] flex flex-col overflow-hidden shadow-2xl border border-slate-200 modal-panel-animate">
        <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between gap-3">
          <div class="flex items-center gap-2.5 min-w-0">
            <span class="px-2 py-0.5 rounded-lg bg-slate-900 text-white font-mono text-xs font-bold">#${esc(tx.id)}</span>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 truncate">Edit Transaksi (${esc(TAB_CONFIG[tx.tab_type]?.label || tx.tab_type)})</h3>
          </div>
          <button type="button" data-close-edit class="w-8 h-8 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold flex items-center justify-center">✕</button>
        </div>

        <div class="p-5 overflow-y-auto grid grid-cols-1 lg:grid-cols-12 gap-5">
          <!-- Kiri: Preview Bukti -->
          <div class="lg:col-span-5 space-y-2.5">
            <div class="rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden min-h-[220px] flex items-center justify-center" data-edit-img-box>
              <p class="text-xs text-slate-400">${files.length ? "Memuat foto bukti..." : "Tidak ada lampiran foto"}</p>
            </div>
            ${
              files.length > 1
                ? `<div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar" data-edit-thumbs>
                    ${files
                      .map(
                        (f, i) =>
                          `<button type="button" data-edit-thumb="${i}" class="px-2.5 py-1 rounded-lg text-[11px] font-semibold shrink-0 ${
                            i === 0 ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                          }">Slot ${esc(f.slot)}</button>`
                      )
                      .join("")}
                  </div>`
                : ""
            }
          </div>

          <!-- Kanan: Form Edit -->
          <form data-edit-form class="lg:col-span-7 space-y-3.5">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 p-3.5 rounded-2xl bg-slate-50 border border-slate-200/80">
              <div>
                <label class="block text-[11px] font-semibold text-slate-600 mb-1">Nominal Pokok${lockTag("nominal_pokok")}</label>
                <input type="number" min="0" name="nominal_pokok" value="${esc(tx.nominal_pokok)}" ${locked.has("nominal_pokok") ? "disabled" : "required"} data-edit-part class="${INPUT_CLS} font-mono" />
              </div>
              <div>
                <label class="block text-[11px] font-semibold text-slate-600 mb-1">Admin / Kode Unik${lockTag("biaya_admin_kode_unik")}</label>
                <input type="number" min="0" name="biaya_admin_kode_unik" value="${esc(tx.biaya_admin_kode_unik)}" ${locked.has("biaya_admin_kode_unik") ? "disabled" : "required"} data-edit-part class="${INPUT_CLS} font-mono" />
              </div>
              <div>
                <label class="block text-[11px] font-semibold text-slate-600 mb-1">Total Mutasi${lockTag("total_mutasi")}</label>
                <input type="number" min="1" name="total_mutasi" value="${esc(tx.total_mutasi)}" ${locked.has("total_mutasi") ? "disabled" : "readonly required"} class="${INPUT_CLS} font-mono font-bold bg-white" />
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Tanggal${lockTag("tanggal_transaksi")}</label>
                <input type="date" name="tanggal_transaksi" value="${esc(tx.tanggal_transaksi)}" ${locked.has("tanggal_transaksi") ? "disabled" : "required"} class="${INPUT_CLS}" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Waktu (WIB)${lockTag("waktu_transaksi")}</label>
                <input type="time" step="1" name="waktu_transaksi" value="${esc(tx.waktu_transaksi)}" ${locked.has("waktu_transaksi") ? "disabled" : "required"} class="${INPUT_CLS}" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Tipe${lockTag("tipe")}</label>
                <select name="tipe" data-edit-tipe ${locked.has("tipe") ? "disabled" : ""} class="${INPUT_CLS}">
                  ${["KELUAR", "MASUK", "PINDAH_BUKU"]
                    .map((t) => `<option value="${t}" ${tx.tipe === t ? "selected" : ""}>${t}</option>`)
                    .join("")}
                </select>
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Rekening Sumber${lockTag("rekening_sumber_id")}</label>
                <select name="rekening_sumber_id" ${locked.has("rekening_sumber_id") ? "disabled" : "required"} class="${INPUT_CLS}">
                  ${accounts
                    .map(
                      (acc) =>
                        `<option value="${acc.id}" ${Number(tx.rekening_sumber_id) === acc.id ? "selected" : ""}>${esc(acc.kode_akun)} (${esc(acc.no_rekening)})</option>`
                    )
                    .join("")}
                </select>
              </div>
              <div data-edit-tujuan-wrap class="${tx.tipe === "PINDAH_BUKU" ? "" : "hidden"} sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Rekening Tujuan${lockTag("rekening_tujuan_id")}</label>
                <select name="rekening_tujuan_id" ${locked.has("rekening_tujuan_id") ? "disabled" : ""} class="${INPUT_CLS}">
                  <option value="">-- Pilih Rekening Tujuan --</option>
                  ${accounts
                    .map(
                      (acc) =>
                        `<option value="${acc.id}" ${Number(tx.rekening_tujuan_id) === acc.id ? "selected" : ""}>${esc(acc.kode_akun)} (${esc(acc.no_rekening)})</option>`
                    )
                    .join("")}
                </select>
              </div>
              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Kategori SOP${lockTag("kategori_id")}</label>
                <select name="kategori_id" ${locked.has("kategori_id") ? "disabled" : "required"} class="${INPUT_CLS}">
                  ${categories
                    .map(
                      (cat) =>
                        `<option value="${cat.id}" ${Number(tx.kategori_id) === cat.id ? "selected" : ""}>${cat.no_urut}. ${esc(cat.nama_kategori)}</option>`
                    )
                    .join("")}
                </select>
              </div>
              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Penerima / Pengirim</label>
                <input type="text" name="penerima_pengirim" value="${esc(tx.penerima_pengirim || "")}" class="${INPUT_CLS}" />
              </div>
              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Keterangan</label>
                <textarea name="keterangan" rows="2" class="w-full p-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition">${esc(tx.keterangan || "")}</textarea>
              </div>
            </div>

            <p data-edit-err class="hidden rounded-xl bg-rose-50 border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700"></p>

            <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
              <button type="button" data-close-edit class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition">Batal</button>
              <button type="submit" data-edit-submit class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-bold transition">Simpan Perubahan</button>
            </div>
          </form>
        </div>
      </div>
    `;

    const blobUrls = new Map();
    const close = () => {
      for (const u of blobUrls.values()) URL.revokeObjectURL(u);
      modal.remove();
    };
    modal.addEventListener("click", (e) => {
      if (e.target === modal || e.target.closest("[data-close-edit]")) close();
    });
    document.body.appendChild(modal);

    const imgBox = modal.querySelector("[data-edit-img-box]");
    async function showFile(idx) {
      const f = files[idx];
      if (!f || !imgBox) return;
      modal.querySelectorAll("[data-edit-thumb]").forEach((b) => {
        const act = Number(b.dataset.editThumb) === idx;
        b.className = `px-2.5 py-1 rounded-lg text-[11px] font-semibold shrink-0 ${
          act ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
        }`;
      });
      try {
        let u = blobUrls.get(f.id);
        if (!u) {
          const res = await apiFetch(String(f.url).replace(/^\/api\/v1/, ""), {}, onUnauthorized);
          if (!res.ok) throw new Error("Gagal memuat foto");
          u = URL.createObjectURL(await res.blob());
          blobUrls.set(f.id, u);
        }
        imgBox.innerHTML = `<img src="${u}" alt="${esc(f.orig_filename)}" class="max-h-[340px] w-full object-contain" />`;
      } catch (err) {
        imgBox.innerHTML = `<p class="text-xs text-rose-600 font-semibold">${esc(err.message)}</p>`;
      }
    }
    if (files.length) showFile(0);
    modal.querySelectorAll("[data-edit-thumb]").forEach((btn) => {
      btn.addEventListener("click", () => showFile(Number(btn.dataset.editThumb)));
    });

    const form = modal.querySelector("[data-edit-form]");
    const tipeEl = form.querySelector("[data-edit-tipe]");
    const tujuanWrap = form.querySelector("[data-edit-tujuan-wrap]");
    tipeEl?.addEventListener("change", () => {
      tujuanWrap?.classList.toggle("hidden", tipeEl.value !== "PINDAH_BUKU");
    });

    const totalEl = form.elements["total_mutasi"];
    form.querySelectorAll("[data-edit-part]").forEach((inp) => {
      inp.addEventListener("input", () => {
        if (!totalEl || totalEl.disabled) return;
        const nom = Number(form.elements["nominal_pokok"]?.value || 0);
        const fee = Number(form.elements["biaya_admin_kode_unik"]?.value || 0);
        totalEl.value = String(nom + fee);
      });
    });

    const errEl = form.querySelector("[data-edit-err]");
    const submitBtn = form.querySelector("[data-edit-submit]");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (submitBtn.disabled) return;
      errEl.classList.add("hidden");

      const getVal = (name) => (locked.has(name) ? tx[name] : form.elements[name]?.value);
      const tipeVal = String(getVal("tipe") || tx.tipe);
      const nomVal = Number(getVal("nominal_pokok") ?? tx.nominal_pokok);
      const feeVal = Number(getVal("biaya_admin_kode_unik") ?? tx.biaya_admin_kode_unik);
      const totVal = locked.has("total_mutasi")
        ? Number(tx.total_mutasi)
        : Number(getVal("total_mutasi") || nomVal + feeVal);
      const tujRaw = getVal("rekening_tujuan_id");

      const body = {
        tanggal_transaksi: String(getVal("tanggal_transaksi") || tx.tanggal_transaksi),
        waktu_transaksi: normalizeTime(String(getVal("waktu_transaksi") || tx.waktu_transaksi)),
        rekening_sumber_id: Number(getVal("rekening_sumber_id")),
        rekening_tujuan_id: tipeVal === "PINDAH_BUKU" && tujRaw ? Number(tujRaw) : null,
        tipe: tipeVal,
        kategori_id: Number(getVal("kategori_id")),
        penerima_pengirim: String(form.elements["penerima_pengirim"]?.value || ""),
        keterangan: String(form.elements["keterangan"]?.value || ""),
        nominal_pokok: nomVal,
        biaya_admin_kode_unik: feeVal,
        total_mutasi: totVal,
      };

      submitBtn.disabled = true;
      submitBtn.textContent = "Menyimpan...";
      try {
        const res = await apiFetch(
          `/struk/${tx.id}`,
          {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          },
          onUnauthorized
        );
        const data = await res.json();
        if (!res.ok) {
          errEl.textContent = parseErrorDetail(data, "Gagal memperbarui transaksi").message;
          errEl.classList.remove("hidden");
          submitBtn.disabled = false;
          submitBtn.textContent = "Simpan Perubahan";
          return;
        }
        close();
        state.recentNotice = `Transaksi #${tx.id} berhasil diperbarui.`;
        await loadRecent();
        render();
      } catch (err) {
        errEl.textContent = err.message || "Gagal memperbarui transaksi";
        errEl.classList.remove("hidden");
        submitBtn.disabled = false;
        submitBtn.textContent = "Simpan Perubahan";
      }
    });
  }

  function renderTopBar() {
    const recentCount = (state.recentItems || []).length;
    return `
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-lg font-bold text-slate-900 tracking-tight">Input Struk Transaksi</h2>
          <p class="text-xs text-slate-500">Upload bukti struk, validasi hasil AI, lalu simpan ke pembukuan.</p>
        </div>
        <div class="inline-flex p-1 rounded-2xl bg-slate-200/75 self-start sm:self-auto">
          <button
            type="button"
            data-switch-view="wizard"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold transition ${
              state.view === "wizard" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            + Input Baru
          </button>
          <button
            type="button"
            data-switch-view="recent"
            class="h-8 px-3.5 rounded-xl text-xs font-semibold transition inline-flex items-center gap-1.5 ${
              state.view === "recent" ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
            }"
          >
            <span>Riwayat</span>
            <span class="px-1.5 py-0.2 rounded-md text-[10px] font-bold ${
              state.view === "recent" ? "bg-slate-900 text-white" : "bg-slate-300/80 text-slate-700"
            }">${recentCount}</span>
          </button>
        </div>
      </div>
    `;
  }

  function renderStepProgress() {
    const steps = ["Upload Struk", "Review & Validasi", "Selesai"];
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

  function renderDropzone(slotKey, cfg) {
    if (!cfg) return "";
    const files = state.files[slotKey] || [];
    return `
      <div
        data-dropzone="${slotKey}"
        class="rounded-2xl border border-slate-200 bg-slate-50/60 p-4 flex flex-col justify-between gap-3 transition"
      >
        <div class="flex items-start justify-between gap-2">
          <div>
            <div class="flex items-center gap-1.5">
              <span class="px-1.5 py-0.5 rounded-md bg-slate-900 text-white text-[10px] font-bold">Slot ${slotKey}</span>
              <h3 class="text-xs font-bold text-slate-900">${esc(cfg.title)}</h3>
            </div>
            <p class="text-[11px] text-slate-500 mt-1">${esc(cfg.sub)}</p>
          </div>
          <span class="shrink-0 px-2 py-0.5 rounded-full text-[10px] font-bold ${
            cfg.required ? "bg-amber-100 text-amber-800" : "bg-slate-200/80 text-slate-600"
          }">${cfg.required ? "Wajib" : "Opsional"}</span>
        </div>

        ${
          files.length
            ? `<div class="grid grid-cols-3 gap-2">
                ${files
                  .map((file, idx) => {
                    const url = previewUrl(file);
                    return `
                      <div class="relative group rounded-xl bg-white border border-slate-200 overflow-hidden aspect-square">
                        <button type="button" data-zoom-local="${slotKey}:${idx}" class="w-full h-full block">
                          <img src="${url}" alt="${esc(file.name)}" class="w-full h-full object-cover" />
                        </button>
                        <button
                          type="button"
                          data-remove-file="${slotKey}:${idx}"
                          aria-label="Hapus ${esc(file.name)}"
                          class="absolute top-1 right-1 w-5 h-5 rounded-full bg-slate-900/75 hover:bg-rose-600 text-white text-[10px] font-bold flex items-center justify-center transition"
                        >✕</button>
                      </div>
                    `;
                  })
                  .join("")}
                ${
                  !cfg.exactOne
                    ? `<label class="rounded-xl border-2 border-dashed border-slate-300 hover:border-blue-500 bg-white flex flex-col items-center justify-center aspect-square cursor-pointer text-slate-400 hover:text-blue-600 transition">
                        <span class="text-lg font-bold leading-none">+</span>
                        <span class="text-[10px] font-semibold mt-0.5">Tambah</span>
                        <input type="file" accept="image/*" multiple data-slot-input="${slotKey}" class="hidden" />
                      </label>`
                    : ""
                }
              </div>`
            : `<label class="rounded-xl border-2 border-dashed border-slate-300 hover:border-blue-500 bg-white px-4 py-6 flex flex-col items-center justify-center text-center cursor-pointer transition group">
                <div class="w-9 h-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center mb-2 group-hover:scale-105 transition">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 16V4m0 0l-4 4m4-4l4 4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>
                  </svg>
                </div>
                <span class="text-xs font-semibold text-slate-800">Pilih atau tarik foto ke sini</span>
                <span class="text-[11px] text-slate-400 mt-0.5">${cfg.exactOne ? "Tepat 1 gambar" : "Bisa pilih banyak gambar"}</span>
                <input type="file" accept="image/*" ${cfg.multiple ? "multiple" : ""} data-slot-input="${slotKey}" class="hidden" />
              </label>`
        }
      </div>
    `;
  }

  function renderStep1() {
    const cfg = TAB_CONFIG[state.tabType];
    const ready = canExtract();

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
        ${renderStepProgress()}

        <!-- Segmented Mode Selector -->
        <div class="space-y-2.5">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-2 p-1 rounded-2xl bg-slate-100">
            ${Object.entries(TAB_CONFIG)
              .map(([key, item]) => {
                const active = state.tabType === key;
                return `
                  <button
                    type="button"
                    data-select-tab="${key}"
                    class="h-10 px-3 rounded-xl text-xs font-semibold inline-flex items-center justify-center gap-2 transition ${
                      active ? "bg-white text-slate-900 shadow-xs" : "text-slate-600 hover:text-slate-900"
                    }"
                  >
                    ${item.icon}
                    <span>${esc(item.label)}</span>
                  </button>
                `;
              })
              .join("")}
          </div>

          <div class="flex flex-wrap items-center justify-between gap-2 px-1">
            <p class="text-xs text-slate-500">${esc(cfg.hint)}</p>
            ${
              state.tabType === "normal"
                ? `<label class="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-amber-50 border border-amber-200 cursor-pointer select-none">
                    <input type="checkbox" data-cash-toggle ${state.isCash ? "checked" : ""} class="rounded border-amber-400 text-slate-900 focus:ring-slate-900" />
                    <span class="text-[11px] font-semibold text-amber-900">Pembayaran Tunai (Kas Operasional)</span>
                  </label>`
                : ""
            }
          </div>
        </div>

        <!-- Upload Dropzones -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          ${renderDropzone("A", cfg.slotA)}
          ${renderDropzone("B", cfg.slotB)}
        </div>

        ${
          cfg.slotC
            ? state.showOptionalSlotC || state.files.C.length > 0
              ? renderDropzone("C", cfg.slotC)
              : `<button type="button" data-show-slot-c class="text-xs font-semibold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1 px-1">
                  <span>+ Tambah Nota / Resi Pendukung (Slot C, opsional)</span>
                </button>`
            : ""
        }

        ${
          state.extractError
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-4 py-3 text-xs text-rose-800 space-y-1">
                <p class="font-bold">${esc(state.extractError)}</p>
                ${
                  state.extractErrors.length > 1
                    ? `<ul class="list-disc pl-4 space-y-0.5">${state.extractErrors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>`
                    : ""
                }
              </div>`
            : ""
        }

        <div class="flex items-center justify-end pt-1">
          <button
            type="button"
            data-extract-btn
            ${state.isExtracting || !ready ? "disabled" : ""}
            class="h-11 px-6 rounded-2xl bg-slate-900 hover:bg-slate-800 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs inline-flex items-center gap-2 transition"
          >
            ${
              state.isExtracting
                ? `<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path></svg><span>Membaca Struk...</span>`
                : `<span>Proses &amp; Cek Struk →</span>`
            }
          </button>
        </div>
      </div>
    `;
  }

  function renderStep2() {
    const res = state.extractResult;
    if (!res) return "";
    const extracted = res.extracted || {};
    const locked = new Set(res.locked_fields || []);
    const errors = res.errors || [];
    const warnings = res.warnings || [];
    const hint = res.mutasi_hint;
    const isBlocked = errors.length > 0;

    const accounts = state.metadata?.rekening_perusahaan || [];
    const categories = (state.metadata?.kategori_sop || []).filter((cat) =>
      res.tab_type === "slip_gaji" ? SALARY_CATEGORIES.has(cat.nama_kategori) : true
    );

    const flatPhotos = [];
    for (const slotKey of ["A", "B", "C"]) {
      const items = res.slots?.[slotKey] || [];
      const files = state.files[slotKey] || [];
      items.forEach((item, idx) => {
        flatPhotos.push({ slotKey, item, file: files[idx] || null });
      });
    }
    const activeIdx = Math.min(state.activePhotoIdx, Math.max(0, flatPhotos.length - 1));
    const activePhoto = flatPhotos[activeIdx];
    const activeUrl = activePhoto?.file ? previewUrl(activePhoto.file) : null;

    const lockIcon = (field) =>
      locked.has(field)
        ? `<span title="Terkunci oleh aturan ${esc(res.tab_type)}">${ICON_LOCK}</span>`
        : "";

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
        ${renderStepProgress()}

        ${
          errors.length
            ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 p-4 space-y-1">
                <p class="text-xs font-bold text-rose-900">Tidak dapat disimpan — perbaiki masalah berikut:</p>
                <ul class="list-disc pl-4 text-xs text-rose-800 space-y-0.5">${errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>
              </div>`
            : ""
        }

        ${
          warnings.length
            ? `<div class="rounded-2xl bg-amber-50 border border-amber-200 p-4 space-y-1">
                <p class="text-xs font-bold text-amber-900">Perhatian:</p>
                <ul class="list-disc pl-4 text-xs text-amber-800 space-y-0.5">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
              </div>`
            : ""
        }

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          <!-- Kiri: Viewer Foto dengan Switcher Thumbnail -->
          <div class="lg:col-span-5 lg:sticky lg:top-20 space-y-3">
            <div class="rounded-2xl border border-slate-200 bg-slate-50 overflow-hidden">
              ${
                activePhoto
                  ? `
                    <div class="px-3.5 py-2.5 bg-white border-b border-slate-100 flex items-center justify-between gap-2">
                      <div class="flex items-center gap-2 min-w-0">
                        <span class="px-2 py-0.5 rounded-md bg-slate-900 text-white text-[10px] font-bold shrink-0">Slot ${esc(activePhoto.slotKey)}</span>
                        <span class="text-xs font-semibold text-slate-800 truncate">${esc(activePhoto.item.orig_filename)}</span>
                      </div>
                      <span class="font-mono text-xs font-bold text-slate-900 shrink-0">${formatRp(activePhoto.item.amount)}</span>
                    </div>
                    ${
                      activeUrl
                        ? `<button type="button" data-zoom-active class="w-full bg-slate-100 flex items-center justify-center max-h-[380px] overflow-hidden cursor-zoom-in">
                            <img src="${activeUrl}" alt="${esc(activePhoto.item.orig_filename)}" class="w-full max-h-[380px] object-contain" />
                          </button>`
                        : ""
                    }
                    <div class="px-3.5 py-2 bg-white border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-500">
                      <span>${esc(activePhoto.item.document_type || "-")}</span>
                      <span>${esc(activePhoto.item.date || "-")} ${esc(activePhoto.item.time || "")}</span>
                    </div>
                  `
                  : ""
              }
            </div>

            ${
              flatPhotos.length > 1
                ? `<div class="flex items-center gap-2 overflow-x-auto no-scrollbar pb-1">
                    ${flatPhotos
                      .map((p, i) => {
                        const thumbUrl = p.file ? previewUrl(p.file) : null;
                        const active = i === activeIdx;
                        return `
                          <button
                            type="button"
                            data-select-photo="${i}"
                            class="relative shrink-0 w-16 h-16 rounded-xl overflow-hidden border-2 transition ${
                              active ? "border-slate-900 ring-2 ring-slate-900/15" : "border-slate-200 opacity-75 hover:opacity-100"
                            }"
                          >
                            ${thumbUrl ? `<img src="${thumbUrl}" alt="" class="w-full h-full object-cover" />` : ""}
                            <span class="absolute bottom-0.5 left-0.5 px-1 rounded bg-slate-900/80 text-white text-[9px] font-bold">${esc(p.slotKey)}</span>
                          </button>
                        `;
                      })
                      .join("")}
                  </div>`
                : ""
            }
          </div>

          <!-- Kanan: Form Review -->
          <form data-save-form class="lg:col-span-7 space-y-4">
            <!-- Ringkasan Nominal + Status Mutasi -->
            <div class="rounded-2xl bg-slate-50 border border-slate-200/90 p-4 space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-500">Total Mutasi Bank</p>
                  <p data-total-display class="text-2xl font-extrabold font-mono text-slate-900 tabular-nums">${formatRp(extracted.total_mutasi ?? 0)}</p>
                </div>
                ${
                  hint
                    ? `<span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold ${
                        hint.found ? "bg-emerald-100 text-emerald-800" : "bg-slate-200/80 text-slate-700"
                      }">
                        <span class="w-1.5 h-1.5 rounded-full ${hint.found ? "bg-emerald-600" : "bg-slate-500"}"></span>
                        ${esc(hint.message)}
                      </span>`
                    : ""
                }
              </div>

              ${renderAiCostCard(res.ai_usage, { contextLabel: "Biaya Token AI (Ekstraksi Struk)" })}

              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2 border-t border-slate-200/70">
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 mb-1">Nominal Pokok${lockIcon("nominal_pokok")}</label>
                  <input type="number" min="0" name="nominal_pokok" value="${esc(extracted.nominal_pokok ?? 0)}" ${locked.has("nominal_pokok") ? "disabled" : "required"} data-amount-part class="${INPUT_CLS} font-mono" />
                </div>
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 mb-1">Admin / Kode Unik${lockIcon("biaya_admin_kode_unik")}</label>
                  <input type="number" min="0" name="biaya_admin_kode_unik" value="${esc(extracted.biaya_admin_kode_unik ?? 0)}" ${locked.has("biaya_admin_kode_unik") ? "disabled" : "required"} data-amount-part class="${INPUT_CLS} font-mono" />
                </div>
                <div>
                  <label class="block text-[11px] font-semibold text-slate-600 mb-1">Total Mutasi${lockIcon("total_mutasi")}</label>
                  <input type="number" min="1" name="total_mutasi" value="${esc(extracted.total_mutasi ?? 0)}" ${locked.has("total_mutasi") ? "disabled" : "readonly required"} class="${INPUT_CLS} font-mono font-bold bg-white" />
                </div>
              </div>
            </div>

            <!-- Detail Transaksi -->
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Tanggal${lockIcon("tanggal_transaksi")}</label>
                <input type="date" name="tanggal_transaksi" value="${esc(extracted.tanggal_transaksi || "")}" ${locked.has("tanggal_transaksi") ? "disabled" : "required"} class="${INPUT_CLS}" />
              </div>

              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Waktu (WIB)${lockIcon("waktu_transaksi")}</label>
                <input type="time" step="1" name="waktu_transaksi" value="${esc(extracted.waktu_transaksi || "12:00:00")}" ${locked.has("waktu_transaksi") ? "disabled" : "required"} class="${INPUT_CLS}" />
              </div>

              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Tipe${lockIcon("tipe")}</label>
                <select name="tipe" data-tipe-select ${locked.has("tipe") ? "disabled" : ""} class="${INPUT_CLS}">
                  ${["KELUAR", "MASUK", "PINDAH_BUKU"]
                    .map((t) => `<option value="${t}" ${extracted.tipe === t ? "selected" : ""}>${t}</option>`)
                    .join("")}
                </select>
              </div>

              <div>
                <label class="block text-xs font-semibold text-slate-700 mb-1">Rekening Sumber${lockIcon("rekening_sumber_id")}</label>
                <select name="rekening_sumber_id" ${locked.has("rekening_sumber_id") ? "disabled" : "required"} class="${INPUT_CLS}">
                  <option value="">-- Pilih Rekening --</option>
                  ${accounts
                    .map(
                      (acc) =>
                        `<option value="${acc.id}" ${Number(extracted.rekening_sumber_id) === acc.id ? "selected" : ""}>${esc(acc.kode_akun)} (${esc(acc.no_rekening)})</option>`
                    )
                    .join("")}
                </select>
              </div>

              <div data-tujuan-wrap class="${extracted.tipe === "PINDAH_BUKU" ? "" : "hidden"} sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Rekening Tujuan${lockIcon("rekening_tujuan_id")}</label>
                <select name="rekening_tujuan_id" ${locked.has("rekening_tujuan_id") ? "disabled" : ""} class="${INPUT_CLS}">
                  <option value="">-- Pilih Rekening Tujuan --</option>
                  ${accounts
                    .map(
                      (acc) =>
                        `<option value="${acc.id}" ${Number(extracted.rekening_tujuan_id) === acc.id ? "selected" : ""}>${esc(acc.kode_akun)} (${esc(acc.no_rekening)})</option>`
                    )
                    .join("")}
                </select>
              </div>

              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Kategori SOP${lockIcon("kategori_id")}</label>
                <select name="kategori_id" ${locked.has("kategori_id") ? "disabled" : "required"} class="${INPUT_CLS}">
                  <option value="">-- Pilih Kategori --</option>
                  ${categories
                    .map(
                      (cat) =>
                        `<option value="${cat.id}" ${Number(extracted.kategori_id) === cat.id ? "selected" : ""}>${cat.no_urut}. ${esc(cat.nama_kategori)}</option>`
                    )
                    .join("")}
                </select>
              </div>

              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Penerima / Pengirim</label>
                <input type="text" name="penerima_pengirim" value="${esc(extracted.penerima_pengirim || "")}" class="${INPUT_CLS}" />
              </div>

              <div class="sm:col-span-2">
                <label class="block text-xs font-semibold text-slate-700 mb-1">Keterangan</label>
                <textarea name="keterangan" rows="2" class="w-full p-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition">${esc(extracted.keterangan || "")}</textarea>
              </div>
            </div>

            ${
              extracted.notes
                ? `<p class="text-[11px] text-slate-500 px-1"><span class="font-semibold text-slate-700">Catatan AI:</span> ${esc(extracted.notes)}</p>`
                : ""
            }

            ${
              state.needsDuplicateForce
                ? `<label class="flex items-start gap-2.5 p-3.5 rounded-2xl bg-amber-50 border border-amber-200 cursor-pointer">
                    <input type="checkbox" name="force_save_duplicate" class="mt-0.5 rounded border-amber-400" />
                    <span class="text-xs font-semibold text-amber-950">Saya yakin transaksi ini bukan duplikat dan tetap ingin menyimpan.</span>
                  </label>`
                : ""
            }

            ${
              state.saveError
                ? `<div class="rounded-2xl bg-rose-50 border border-rose-200 px-3.5 py-2.5 text-xs font-semibold text-rose-700">${esc(state.saveError)}</div>`
                : ""
            }

            <div class="flex items-center justify-between gap-3 pt-3 border-t border-slate-100">
              <button type="button" data-back-step1 class="h-10 px-4 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition">
                ← Ganti Foto
              </button>
              <button
                type="submit"
                data-save-btn
                ${isBlocked || state.isSaving ? "disabled" : ""}
                class="h-10 px-6 rounded-xl bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 text-white text-xs font-bold shadow-xs transition"
              >
                ${isBlocked ? "Diblokir Aturan" : state.isSaving ? "Menyimpan..." : "Simpan Transaksi"}
              </button>
            </div>
          </form>
        </div>
      </div>
    `;
  }

  function renderStep3() {
    const res = state.saveResult;
    if (!res) return "";
    const statusKey = res.reconciliation?.status_rekonsiliasi || "BELUM_REKON";
    const recon = RECON_BADGE[statusKey] || RECON_BADGE.BELUM_REKON;

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
              Transaksi #${esc(res.transaksi_id)}
            </span>
            <h3 class="text-lg font-bold text-slate-900">Transaksi Berhasil Disimpan</h3>
            <p class="text-xs text-slate-500">${(res.files || []).length} file bukti telah dicatat ke pembukuan.</p>
          </div>

          <div class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-bold ${recon.cls}">
            <span>Status Rekonsiliasi: ${esc(recon.label)}</span>
          </div>

          ${
            res.ai_usage && Number(res.ai_usage.total_tokens || 0) > 0
              ? `<div class="text-left">${renderAiCostCard(res.ai_usage, { contextLabel: "Biaya Token AI Transaksi Ini" })}</div>`
              : ""
          }

          <div class="flex flex-wrap items-center justify-center gap-2 pt-2">
            <button type="button" data-new-input class="h-10 px-5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition">
              + Input Struk Lagi
            </button>
            <button type="button" data-switch-view="recent" class="h-10 px-4 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition">
              Lihat Riwayat
            </button>
          </div>
        </div>
      </div>
    `;
  }

  function renderRecentView() {
    const query = state.recentSearch.trim().toLowerCase();
    const allItems = state.recentItems || [];
    const items = allItems.filter((tx) => {
      if (state.recentFilter === "unreconciled" && tx.status_rekonsiliasi !== "BELUM_REKON") {
        return false;
      }
      if (state.recentFilter === "reconciled" && tx.status_rekonsiliasi === "BELUM_REKON") {
        return false;
      }
      if (!query) return true;
      const blob = `${tx.id} ${tx.penerima_pengirim} ${tx.keterangan} ${tx.nama_kategori} ${tx.rekening_sumber} ${tx.rekening_tujuan || ""} ${tx.tab_type}`.toLowerCase();
      return blob.includes(query);
    });

    const totalSum = items.reduce((acc, tx) => acc + Number(tx.total_mutasi || 0), 0);
    const totalAiTokens = items.reduce((acc, tx) => acc + Number(tx.ai_usage?.total_tokens || 0), 0);
    const totalAiIdr = items.reduce((acc, tx) => acc + Number(tx.ai_usage?.cost_idr || 0), 0);
    const amountColor = (tipe) =>
      tipe === "MASUK" ? "text-emerald-700" : tipe === "PINDAH_BUKU" ? "text-indigo-700" : "text-slate-900";
    const amountPrefix = (tipe) => (tipe === "MASUK" ? "+" : tipe === "KELUAR" ? "-" : "");

    return `
      <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
        <!-- Toolbar Riwayat -->
        <div class="p-4 sm:p-5 border-b border-slate-100 space-y-3.5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex items-center gap-2 overflow-x-auto no-scrollbar">
              ${[
                { id: "all", label: `Semua (${allItems.length})` },
                { id: "unreconciled", label: "Belum Rekon" },
                { id: "reconciled", label: "Sudah Cocok" },
              ]
                .map((f) => {
                  const active = state.recentFilter === f.id;
                  return `<button type="button" data-recent-filter="${f.id}" class="shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold transition ${
                    active ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200/70"
                  }">${esc(f.label)}</button>`;
                })
                .join("")}
            </div>
            <div class="flex flex-wrap items-center gap-3 text-xs">
              <span class="text-slate-500">Total tampil: <strong class="font-mono text-slate-900 tabular-nums">${formatRp(totalSum)}</strong></span>
              <span class="px-2.5 py-1 rounded-full bg-indigo-50 text-indigo-800 font-mono text-[11px] font-semibold">
                Cost AI: ${esc(formatAiCostIdr(totalAiIdr))} (${formatTokenCount(totalAiTokens)} tok)
              </span>
              <button type="button" data-refresh-recent title="Refresh" class="h-8 px-3 rounded-xl border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-50 inline-flex items-center gap-1.5 transition">
                ${ICON_REFRESH}<span>Refresh</span>
              </button>
            </div>
          </div>

          <div class="relative">
            <svg class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              data-recent-search
              value="${esc(state.recentSearch)}"
              placeholder="Cari penerima, keterangan, kategori, rekening, atau #ID..."
              class="w-full h-10 pl-10 pr-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 placeholder-slate-400 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-600/20 focus:border-blue-600 transition"
            />
          </div>

          ${
            state.recentNotice
              ? `<div class="rounded-xl bg-emerald-50 border border-emerald-200 px-3.5 py-2 text-xs font-semibold text-emerald-800 flex items-center justify-between">
                  <span>${esc(state.recentNotice)}</span>
                  <button type="button" data-dismiss-notice class="text-emerald-600 hover:text-emerald-900 font-bold">✕</button>
                </div>`
              : ""
          }
        </div>

        ${
          state.recentError
            ? `<div class="p-5 text-xs font-semibold text-rose-600">${esc(state.recentError)}</div>`
            : items.length === 0
              ? `<div class="py-12 px-4 text-center space-y-1">
                  <p class="text-sm font-semibold text-slate-700">Tidak ada transaksi ditemukan</p>
                  <p class="text-xs text-slate-400">Ubah kata kunci pencarian atau tambah input struk baru.</p>
                </div>`
              : `
                <!-- Desktop Table -->
                <div class="hidden md:block overflow-x-auto">
                  <table class="w-full text-left border-collapse">
                    <thead>
                      <tr class="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                        <th class="py-3 pl-5 pr-3">Tanggal</th>
                        <th class="py-3 px-3">Transaksi &amp; Kategori</th>
                        <th class="py-3 px-3">Rekening</th>
                        <th class="py-3 px-3 text-right">Nominal</th>
                        <th class="py-3 px-3">Status &amp; Bukti</th>
                        <th class="py-3 pl-3 pr-5 text-right">Aksi</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-xs">
                      ${items
                        .map((tx) => {
                          const canModify = user.role !== "staff" || tx.status_rekonsiliasi === "BELUM_REKON";
                          const recon = RECON_BADGE[tx.status_rekonsiliasi] || RECON_BADGE.BELUM_REKON;
                          const fileCount = (tx.files || []).length;
                          return `
                            <tr class="hover:bg-slate-50/70 transition">
                              <td class="py-3.5 pl-5 pr-3 align-top whitespace-nowrap">
                                <p class="font-mono font-semibold text-slate-900">${esc(tx.tanggal_transaksi)}</p>
                                <p class="font-mono text-[11px] text-slate-400">${esc(tx.waktu_transaksi)} · #${tx.id}</p>
                              </td>
                              <td class="py-3.5 px-3 align-top max-w-[260px]">
                                <p class="font-bold text-slate-900 truncate">${esc(tx.penerima_pengirim || "-")}</p>
                                ${
                                  tx.keterangan
                                    ? `<p class="text-[11px] text-slate-500 truncate mt-0.5">${esc(tx.keterangan)}</p>`
                                    : ""
                                }
                                <div class="flex flex-wrap items-center gap-1.5 mt-1.5">
                                  <span class="px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 text-[10px] font-semibold">${esc(tx.nama_kategori)}</span>
                                  <span class="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-bold uppercase">${esc(tx.tab_type)}</span>
                                  ${renderAiCostRowBadge(tx.ai_usage)}
                                </div>
                              </td>
                              <td class="py-3.5 px-3 align-top whitespace-nowrap">
                                <p class="font-semibold text-slate-800">${esc(tx.rekening_sumber)}${tx.rekening_tujuan ? ` → ${esc(tx.rekening_tujuan)}` : ""}</p>
                                <p class="text-[11px] text-slate-400 mt-0.5">${esc(tx.nama_admin)}</p>
                              </td>
                              <td class="py-3.5 px-3 align-top text-right whitespace-nowrap">
                                <p class="font-mono text-sm font-extrabold tabular-nums ${amountColor(tx.tipe)}">${amountPrefix(tx.tipe)}${formatRp(tx.total_mutasi)}</p>
                                ${
                                  Number(tx.biaya_admin_kode_unik || 0) > 0
                                    ? `<p class="font-mono text-[10px] text-slate-400 mt-0.5">Pokok ${formatRp(tx.nominal_pokok)} + ${formatRp(tx.biaya_admin_kode_unik)}</p>`
                                    : `<p class="text-[10px] font-semibold text-slate-400 mt-0.5">${esc(tx.tipe)}</p>`
                                }
                              </td>
                              <td class="py-3.5 px-3 align-top whitespace-nowrap">
                                <div class="flex flex-col items-start gap-1.5">
                                  <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${recon.cls}">${esc(recon.label)}</span>
                                  ${
                                    fileCount
                                      ? `<button type="button" data-open-gallery="${tx.id}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-[11px] font-semibold text-slate-700 transition">
                                          ${ICON_PHOTO}<span>${fileCount} Foto</span>
                                        </button>`
                                      : `<span class="text-[11px] text-slate-400">Tanpa foto</span>`
                                  }
                                </div>
                              </td>
                              <td class="py-3.5 pl-3 pr-5 align-top text-right whitespace-nowrap">
                                ${
                                  canModify
                                    ? `<div class="inline-flex items-center gap-1">
                                        <button type="button" data-edit-tx="${tx.id}" title="Edit transaksi" class="h-8 px-2.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-100 text-slate-700 text-[11px] font-semibold inline-flex items-center gap-1 transition">
                                          ${ICON_EDIT}<span>Edit</span>
                                        </button>
                                        <button type="button" data-delete-tx="${tx.id}" title="Hapus transaksi" class="h-8 w-8 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-600 inline-flex items-center justify-center transition">
                                          ${ICON_TRASH}
                                        </button>
                                      </div>`
                                    : `<span class="text-[11px] text-slate-400">Terkunci</span>`
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
                    .map((tx) => {
                      const canModify = user.role !== "staff" || tx.status_rekonsiliasi === "BELUM_REKON";
                      const recon = RECON_BADGE[tx.status_rekonsiliasi] || RECON_BADGE.BELUM_REKON;
                      const fileCount = (tx.files || []).length;
                      return `
                        <article class="p-4 space-y-2.5">
                          <div class="flex items-start justify-between gap-2">
                            <div class="min-w-0">
                              <div class="flex items-center gap-1.5">
                                <span class="font-mono text-[11px] text-slate-400">#${tx.id}</span>
                                <span class="font-mono text-[11px] font-semibold text-slate-600">${esc(tx.tanggal_transaksi)}</span>
                                <span class="px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 text-[10px] font-bold uppercase">${esc(tx.tab_type)}</span>
                              </div>
                              <p class="text-sm font-bold text-slate-900 truncate mt-0.5">${esc(tx.penerima_pengirim || tx.keterangan || "-")}</p>
                              <p class="text-[11px] text-slate-500 truncate">${esc(tx.nama_kategori)} · ${esc(tx.rekening_sumber)}${tx.rekening_tujuan ? ` → ${esc(tx.rekening_tujuan)}` : ""}</p>
                            </div>
                            <span class="font-mono text-sm font-extrabold tabular-nums shrink-0 ${amountColor(tx.tipe)}">${amountPrefix(tx.tipe)}${formatRp(tx.total_mutasi)}</span>
                          </div>

                          <div class="flex items-center justify-between gap-2 pt-1">
                            <div class="flex flex-wrap items-center gap-1.5">
                              <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold ${recon.cls}">${esc(recon.label)}</span>
                              ${renderAiCostRowBadge(tx.ai_usage)}
                              ${
                                fileCount
                                  ? `<button type="button" data-open-gallery="${tx.id}" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border border-slate-200 text-[11px] font-semibold text-slate-700">
                                      ${ICON_PHOTO}<span>${fileCount}</span>
                                    </button>`
                                  : ""
                              }
                            </div>
                            ${
                              canModify
                                ? `<div class="flex items-center gap-1.5">
                                    <button type="button" data-edit-tx="${tx.id}" class="h-8 px-3 rounded-lg border border-slate-200 text-xs font-semibold text-slate-700 inline-flex items-center gap-1">${ICON_EDIT}<span>Edit</span></button>
                                    <button type="button" data-delete-tx="${tx.id}" class="h-8 w-8 rounded-lg border border-rose-200 text-rose-600 inline-flex items-center justify-center">${ICON_TRASH}</button>
                                  </div>`
                                : `<span class="text-[10px] text-slate-400">Terkunci</span>`
                            }
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
        if (state.view === "recent") await loadRecent();
        render();
      });
    });

    root.querySelectorAll("[data-select-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.tabType = btn.dataset.selectTab;
        if (state.tabType !== "normal") state.isCash = false;
        if (state.tabType !== "flip") {
          state.files.C = [];
          state.showOptionalSlotC = false;
        }
        if (state.tabType === "flip" && state.files.A.length > 1) {
          state.files.A = state.files.A.slice(0, 1);
        }
        state.extractError = "";
        state.extractErrors = [];
        render();
      });
    });

    root.querySelector("[data-cash-toggle]")?.addEventListener("change", (e) => {
      state.isCash = Boolean(e.target.checked);
    });

    root.querySelector("[data-show-slot-c]")?.addEventListener("click", () => {
      state.showOptionalSlotC = true;
      render();
    });

    root.querySelectorAll("[data-slot-input]").forEach((input) => {
      input.addEventListener("change", (e) => addFilesToSlot(input.dataset.slotInput, e.target.files));
    });

    root.querySelectorAll("[data-dropzone]").forEach((zone) => {
      const slot = zone.dataset.dropzone;
      zone.addEventListener("dragover", (e) => {
        e.preventDefault();
        zone.classList.add("border-blue-500", "bg-blue-50/40");
      });
      zone.addEventListener("dragleave", () => {
        zone.classList.remove("border-blue-500", "bg-blue-50/40");
      });
      zone.addEventListener("drop", (e) => {
        e.preventDefault();
        zone.classList.remove("border-blue-500", "bg-blue-50/40");
        addFilesToSlot(slot, e.dataTransfer?.files);
      });
    });

    root.querySelectorAll("[data-remove-file]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [slot, idx] = btn.dataset.removeFile.split(":");
        removeFileFromSlot(slot, Number(idx));
      });
    });

    root.querySelectorAll("[data-zoom-local]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const [slot, idx] = btn.dataset.zoomLocal.split(":");
        const file = state.files[slot]?.[Number(idx)];
        if (file) showLightbox(file.name, file);
      });
    });

    root.querySelectorAll("[data-select-photo]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const form = root.querySelector("[data-save-form]");
        if (form && state.extractResult?.extracted) {
          const ex = state.extractResult.extracted;
          const locked = new Set(state.extractResult.locked_fields || []);
          for (const key of [
            "tanggal_transaksi",
            "waktu_transaksi",
            "tipe",
            "rekening_sumber_id",
            "rekening_tujuan_id",
            "kategori_id",
            "penerima_pengirim",
            "keterangan",
            "nominal_pokok",
            "biaya_admin_kode_unik",
            "total_mutasi",
          ]) {
            if (!locked.has(key) && form.elements[key]) {
              ex[key] = form.elements[key].value;
            }
          }
        }
        state.activePhotoIdx = Number(btn.dataset.selectPhoto);
        render();
      });
    });

    root.querySelector("[data-zoom-active]")?.addEventListener("click", () => {
      const res = state.extractResult;
      if (!res) return;
      const flat = [];
      for (const s of ["A", "B", "C"]) {
        (res.slots?.[s] || []).forEach((item, idx) => {
          flat.push({ item, file: state.files[s]?.[idx] });
        });
      }
      const chosen = flat[state.activePhotoIdx];
      if (chosen?.file) showLightbox(chosen.item.orig_filename, chosen.file);
    });

    root.querySelector("[data-extract-btn]")?.addEventListener("click", handleExtract);
    root.querySelector("[data-reset-wizard]")?.addEventListener("click", resetWizard);
    root.querySelector("[data-new-input]")?.addEventListener("click", resetWizard);
    root.querySelector("[data-back-step1]")?.addEventListener("click", () => {
      state.step = 1;
      state.saveError = "";
      render();
    });

    const saveForm = root.querySelector("[data-save-form]");
    if (saveForm) {
      const tipeSelect = saveForm.querySelector("[data-tipe-select]");
      const tujuanWrap = saveForm.querySelector("[data-tujuan-wrap]");
      tipeSelect?.addEventListener("change", () => {
        tujuanWrap?.classList.toggle("hidden", tipeSelect.value !== "PINDAH_BUKU");
      });

      const totalDisplay = saveForm.querySelector("[data-total-display]");
      const totalInput = saveForm.elements["total_mutasi"];
      saveForm.querySelectorAll("[data-amount-part]").forEach((inp) => {
        inp.addEventListener("input", () => {
          if (!totalInput || totalInput.disabled) return;
          const nom = Number(saveForm.elements["nominal_pokok"]?.value || 0);
          const fee = Number(saveForm.elements["biaya_admin_kode_unik"]?.value || 0);
          const sum = nom + fee;
          totalInput.value = String(sum);
          if (totalDisplay) totalDisplay.textContent = formatRp(sum);
        });
      });

      saveForm.addEventListener("submit", (e) => {
        e.preventDefault();
        handleSave(saveForm);
      });
    }

    root.querySelector("[data-recent-search]")?.addEventListener("input", (e) => {
      state.recentSearch = e.target.value;
      const cursor = e.target.selectionStart;
      render();
      const next = container.querySelector("[data-recent-search]");
      if (next) {
        next.focus();
        next.setSelectionRange(cursor, cursor);
      }
    });

    root.querySelectorAll("[data-recent-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.recentFilter = btn.dataset.recentFilter;
        render();
      });
    });

    root.querySelector("[data-dismiss-notice]")?.addEventListener("click", () => {
      state.recentNotice = "";
      render();
    });

    root.querySelector("[data-refresh-recent]")?.addEventListener("click", async () => {
      await loadRecent();
      render();
    });

    root.querySelectorAll("[data-open-gallery]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tx = (state.recentItems || []).find((item) => item.id === Number(btn.dataset.openGallery));
        if (tx) openGalleryModal(tx);
      });
    });

    root.querySelectorAll("[data-edit-tx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tx = (state.recentItems || []).find((item) => item.id === Number(btn.dataset.editTx));
        if (tx) openEditModal(tx);
      });
    });

    root.querySelectorAll("[data-view-file]").forEach((btn) => {
      btn.addEventListener("click", () =>
        showLightbox(btn.dataset.fileTitle || "Bukti Transaksi", btn.dataset.viewFile)
      );
    });

    root.querySelectorAll("[data-delete-tx]").forEach((btn) => {
      btn.addEventListener("click", () => handleDelete(Number(btn.dataset.deleteTx)));
    });
  }

  function render() {
    revokePreviews();
    const wrapper = document.createElement("div");
    wrapper.className = "space-y-5 view-animate";
    const mainHtml =
      state.view === "recent"
        ? renderRecentView()
        : state.step === 1
          ? renderStep1()
          : state.step === 2
            ? renderStep2()
            : renderStep3();
    wrapper.innerHTML = `${renderTopBar()}${mainHtml}`;
    container.replaceChildren(wrapper);
    bindEvents(wrapper);
  }

  await Promise.all([loadMetadata(), loadRecent()]);
  render();
}
