import { apiFetch } from "../api.js";
import { fetchMenuPlaceholder } from "./shared.js";
import {
  buildCashReport,
  downloadCashReport,
  formatTanggalId,
  loadExcelJS,
  monthLabel,
  monthRange,
} from "./cashReportExcel.js";

/**
 * Menu Rekonsiliasi: Cash Report bulanan per rekening (format sama dengan file
 * Cash_Report_Operasional-PT_Lokal_Komoditi_Indonesia_2026.xlsx) + tombol Download Excel.
 *
 * Hanya memakai endpoint yang sudah ada:
 *   GET /rekonsiliasi          -> cek hak akses menu
 *   GET /struk/metadata        -> daftar rekening perusahaan
 *   GET /struk/recent?limit=   -> transaksi internal (hasil Input Struk)
 *   GET /mutasi/batches        -> periode & saldo awal/akhir mutasi bank
 *   GET /mutasi/rows           -> baris mutasi bank per rekening & bulan
 */

const RECENT_LIMIT = 100; // batas maksimum dari backend /struk/recent
const MUTASI_ROWS_LIMIT = 500; // batas maksimum dari backend /mutasi/rows

const INPUT_CLS =
  "w-full h-10 px-3 rounded-xl bg-slate-50/70 border border-slate-200 text-xs text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-600/20 focus:border-indigo-600 disabled:bg-slate-100 disabled:text-slate-500 transition";

const TX_STATUS_BADGE = {
  BELUM_REKON: { cls: "bg-slate-100 text-slate-700", label: "Belum Rekon" },
  MUTASI_BELUM_ADA: { cls: "bg-amber-50 text-amber-800", label: "Mutasi Belum Ada" },
  SESUAI: { cls: "bg-emerald-50 text-emerald-700", label: "Sesuai" },
  SELISIH_KODE_UNIK_ADMIN: { cls: "bg-blue-50 text-blue-700", label: "Selisih Admin" },
  PINDAH_BUKU_COCOK: { cls: "bg-indigo-50 text-indigo-700", label: "Pindah Buku Cocok" },
};

const ICON_SHIELD = `<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.9" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0 1 12 2.944a11.955 11.955 0 0 1-8.618 3.04A12.02 12.02 0 0 0 3 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016Z" /></svg>`;
const ICON_DOWNLOAD = `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 4v12m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>`;
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
  if (amount === null || amount === undefined || amount === "") return "-";
  const n = Math.round(Number(amount || 0));
  return `${n < 0 ? "-" : ""}Rp${Math.abs(n).toLocaleString("id-ID")}`;
}

function parseError(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail?.message) return data.detail.message;
  return data.message || fallback;
}

async function getJson(path, onUnauthorized) {
  const res = await apiFetch(path, {}, onUnauthorized);
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const err = new Error(parseError(data, `Gagal memuat ${path}`));
    err.status = res.status;
    throw err;
  }
  return data;
}

function monthKeyOf(isoDate) {
  const match = /^(\d{4})-(\d{2})/.exec(String(isoDate || ""));
  return match ? `${match[1]}-${match[2]}` : null;
}

/**
 * Rekening yang digabung jadi satu pilihan di dropdown.
 * Di database BRI tercatat 2 kali ("BRI" BritAma Bisnis & "BRI Operasional" BRImo);
 * di menu Rekonsiliasi cukup tampil satu: "BRI".
 */
function groupKeyOf(rekening) {
  if (/^BRI\b/i.test(String(rekening.kode_akun || ""))) return "BRI";
  return String(rekening.kode_akun || rekening.id);
}

function buildRekeningOptions(list) {
  const groups = new Map();
  for (const r of list) {
    const key = groupKeyOf(r);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(r);
  }
  return [...groups.entries()].map(([key, members]) => {
    // Rekening utama = yang kode_akun-nya sama persis dengan key (mis. "BRI"), kalau tidak ada pakai yang pertama.
    const main = members.find((m) => m.kode_akun === key) || members[0];
    return {
      id: key,
      ids: members.map((m) => Number(m.id)),
      kode_akun: key,
      bank_lembaga: members.length > 1 ? key === "BRI" ? "Bank BRI" : main.bank_lembaga : main.bank_lembaga,
      no_rekening: members.map((m) => m.no_rekening).filter((n) => n && n !== "-").join(", ") || main.no_rekening,
      is_cash: members.every((m) => m.is_cash),
    };
  });
}

function txTouchesRekening(tx, option) {
  const ids = option ? option.ids : [];
  return ids.includes(Number(tx.rekening_sumber_id)) || ids.includes(Number(tx.rekening_tujuan_id));
}

/* ------------------------------------------------------------------ */

export async function renderRekonsiliasiMenu(container, { onUnauthorized }) {
  // Cek hak akses menu (endpoint lama tetap dipakai).
  await fetchMenuPlaceholder("/rekonsiliasi", onUnauthorized);

  const state = {
    rekening: [],
    transactions: [],
    batches: [],
    mutasiAvailable: true,
    rekeningId: null,
    monthKey: null,
    saldoAwalManual: null, // null = pakai nilai otomatis
    auto: { saldoAwal: 0, sumber: "", saldoAkhirBank: null, mutasiRows: [], mutasiTruncated: false },
    loading: false,
    loadingMutasi: false,
    downloading: false,
    error: "",
    mutasiRequestId: 0,
  };

  const root = document.createElement("section");
  root.className = "view-animate space-y-5";
  root.innerHTML = `
    <div class="rounded-3xl bg-white border border-slate-200/90 p-5 sm:p-6 shadow-2xs space-y-5">
      <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
        <div class="flex items-start gap-3 min-w-0">
          <div class="w-11 h-11 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">${ICON_SHIELD}</div>
          <div class="min-w-0 space-y-1">
            <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700">Tab Rekonsiliasi</span>
            <h2 class="text-lg font-bold text-slate-900">Rekonsiliasi Struk vs Mutasi</h2>
            <p class="text-xs text-slate-500 leading-relaxed">Cash Report bulanan per rekening dari transaksi Input Struk, dibandingkan dengan mutasi bank. Bisa diunduh sebagai Excel dengan format Cash Report Operasional.</p>
          </div>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button type="button" data-action="refresh" class="inline-flex items-center gap-1.5 h-10 px-3 rounded-xl text-xs font-semibold bg-white text-slate-700 border border-slate-200 hover:bg-slate-100 transition disabled:opacity-50">
            ${ICON_REFRESH}<span>Muat Ulang</span>
          </button>
          <button type="button" data-action="download" class="inline-flex items-center gap-1.5 h-10 px-4 rounded-xl text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition disabled:opacity-50 disabled:cursor-not-allowed">
            ${ICON_DOWNLOAD}<span data-download-label>Download Excel</span>
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label class="space-y-1.5">
          <span class="block text-xs font-semibold text-slate-700">Rekening</span>
          <select data-filter="rekening" class="${INPUT_CLS} font-semibold"></select>
        </label>
        <label class="space-y-1.5">
          <span class="block text-xs font-semibold text-slate-700">Bulan</span>
          <select data-filter="month" class="${INPUT_CLS} font-semibold"></select>
        </label>
        <label class="space-y-1.5">
          <span class="flex items-center justify-between gap-2">
            <span class="text-xs font-semibold text-slate-700">Saldo Awal (Rp)</span>
            <button type="button" data-action="reset-saldo" class="hidden text-[11px] font-semibold text-indigo-600 hover:text-indigo-800">Pakai otomatis</button>
          </span>
          <input data-filter="saldo-awal" type="number" step="1" inputmode="numeric" class="${INPUT_CLS} font-mono" />
          <span data-saldo-hint class="block text-[11px] text-slate-500"></span>
        </label>
      </div>

      <div data-alert class="hidden"></div>
    </div>

    <div data-summary class="grid grid-cols-2 lg:grid-cols-4 gap-3"></div>

    <div class="rounded-3xl bg-white border border-slate-200/90 shadow-2xs overflow-hidden">
      <div class="px-5 sm:px-6 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 data-preview-title class="text-sm font-bold text-slate-900">Preview Cash Report</h3>
          <p data-preview-subtitle class="text-xs text-slate-500">-</p>
        </div>
        <span data-row-count class="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700">0 transaksi</span>
      </div>
      <div class="overflow-x-auto max-h-[560px]">
        <table class="w-full text-left border-collapse text-xs min-w-[1100px]">
          <thead class="sticky top-0 z-10 bg-slate-50/95 backdrop-blur-xs border-b border-slate-200 text-[11px] font-bold uppercase tracking-wider text-slate-500">
            <tr>
              <th class="px-3 py-2.5">Tgl Input / Admin</th>
              <th class="px-3 py-2.5">Tgl Transaksi</th>
              <th class="px-3 py-2.5">Keterangan</th>
              <th class="px-3 py-2.5">Kategori</th>
              <th class="px-3 py-2.5">Uang Masuk</th>
              <th class="px-3 py-2.5">Uang Keluar</th>
              <th class="px-3 py-2.5 text-right">Debet</th>
              <th class="px-3 py-2.5 text-right">Kredit</th>
              <th class="px-3 py-2.5 text-right">Saldo</th>
              <th class="px-3 py-2.5">Lampiran</th>
              <th class="px-3 py-2.5">Status Rekon</th>
            </tr>
          </thead>
          <tbody data-tbody class="divide-y divide-slate-100"></tbody>
        </table>
      </div>
    </div>
  `;
  container.replaceChildren(root);

  const el = {
    rekening: root.querySelector('[data-filter="rekening"]'),
    month: root.querySelector('[data-filter="month"]'),
    saldo: root.querySelector('[data-filter="saldo-awal"]'),
    saldoHint: root.querySelector("[data-saldo-hint]"),
    resetSaldo: root.querySelector('[data-action="reset-saldo"]'),
    refresh: root.querySelector('[data-action="refresh"]'),
    download: root.querySelector('[data-action="download"]'),
    downloadLabel: root.querySelector("[data-download-label]"),
    alert: root.querySelector("[data-alert]"),
    summary: root.querySelector("[data-summary]"),
    tbody: root.querySelector("[data-tbody]"),
    previewTitle: root.querySelector("[data-preview-title]"),
    previewSubtitle: root.querySelector("[data-preview-subtitle]"),
    rowCount: root.querySelector("[data-row-count]"),
  };

  const selectedRekening = () => state.rekening.find((r) => String(r.id) === String(state.rekeningId)) || null;

  const effectiveSaldoAwal = () =>
    state.saldoAwalManual === null ? Number(state.auto.saldoAwal || 0) : Number(state.saldoAwalManual || 0);

  const currentReport = () => {
    const rekening = selectedRekening();
    if (!rekening || !state.monthKey) return null;
    return buildCashReport({
      transactions: state.transactions,
      rekening,
      monthKey: state.monthKey,
      saldoAwal: effectiveSaldoAwal(),
    });
  };

  /* ------------------------- Opsi filter ------------------------- */

  function availableMonths() {
    // Selalu tampilkan Januari s/d bulan sekarang (tahun berjalan),
    // ditambah bulan lain yang memang punya data (mis. tahun sebelumnya).
    const keys = new Set();
    const now = new Date();
    for (let m = 1; m <= now.getMonth() + 1; m += 1) {
      keys.add(`${now.getFullYear()}-${String(m).padStart(2, "0")}`);
    }
    for (const tx of state.transactions) {
      const key = monthKeyOf(tx.tanggal_transaksi);
      if (key) keys.add(key);
    }
    for (const b of state.batches) {
      [b.periode_mulai, b.periode_selesai].forEach((d) => {
        const key = monthKeyOf(d);
        if (key) keys.add(key);
      });
    }
    return [...keys].sort().reverse();
  }

  function defaultRekeningId() {
    if (!state.rekening.length) return null;
    const countFor = (option) => state.transactions.filter((tx) => txTouchesRekening(tx, option)).length;
    let best = state.rekening[0];
    for (const r of state.rekening) {
      if (countFor(r) > countFor(best)) best = r;
    }
    return best.id;
  }

  function defaultMonthFor(option) {
    const months = state.transactions
      .filter((tx) => txTouchesRekening(tx, option))
      .map((tx) => monthKeyOf(tx.tanggal_transaksi))
      .filter(Boolean)
      .sort();
    return months.length ? months[months.length - 1] : availableMonths()[0];
  }

  function countTxPerMonth(option) {
    const map = new Map();
    for (const tx of state.transactions) {
      if (!txTouchesRekening(tx, option)) continue;
      const key = monthKeyOf(tx.tanggal_transaksi);
      if (key) map.set(key, (map.get(key) || 0) + 1);
    }
    return map;
  }

  function renderFilterOptions() {
    el.rekening.innerHTML = state.rekening
      .map(
        (r) =>
          `<option value="${esc(r.id)}" ${String(r.id) === String(state.rekeningId) ? "selected" : ""}>${esc(r.kode_akun)} — ${esc(r.bank_lembaga)}</option>`
      )
      .join("");

    const counts = countTxPerMonth(selectedRekening());
    el.month.innerHTML = availableMonths()
      .map((key) => {
        const n = counts.get(key) || 0;
        return `<option value="${key}" ${key === state.monthKey ? "selected" : ""}>${esc(monthLabel(key))}${n ? ` (${n} transaksi)` : ""}</option>`;
      })
      .join("");
  }

  /* ------------------------- Saldo otomatis ------------------------- */

  /** Saldo awal/akhir bank untuk SATU id rekening di bulan terpilih. */
  function saldoFromMutasi(rekId, rows, truncated, start, end) {
    const own = state.batches.filter((b) => Number(b.rekening_id) === rekId);
    const firstBatch = own
      .filter((b) => b.periode_mulai >= start && b.periode_mulai <= end)
      .filter((b) => b.saldo_awal_periode !== null && b.saldo_awal_periode !== undefined)
      .sort((a, b) => a.periode_mulai.localeCompare(b.periode_mulai))[0];
    const lastBatch = own
      .filter((b) => b.periode_selesai >= start && b.periode_selesai <= end)
      .filter((b) => b.saldo_akhir_periode !== null && b.saldo_akhir_periode !== undefined)
      .sort((a, b) => b.periode_selesai.localeCompare(a.periode_selesai))[0];

    // baris mutasi diurutkan terbaru dulu oleh backend
    const oldest = rows[rows.length - 1];
    const newest = rows[0];
    const result = { saldoAwal: null, sumber: "", saldoAkhir: null };

    if (firstBatch) {
      result.saldoAwal = Number(firstBatch.saldo_awal_periode);
      result.sumber = `saldo awal mutasi "${firstBatch.nama_file}"`;
    } else if (oldest && !truncated && oldest.saldo !== null && oldest.saldo !== undefined) {
      const nominal = Number(oldest.nominal || 0);
      result.saldoAwal = Number(oldest.saldo) + (oldest.tipe === "CR" ? -nominal : nominal);
      result.sumber = `mutasi pertama ${formatTanggalId(oldest.tanggal)}`;
    }

    if (lastBatch) {
      result.saldoAkhir = Number(lastBatch.saldo_akhir_periode);
    } else if (newest && newest.saldo !== null && newest.saldo !== undefined) {
      result.saldoAkhir = Number(newest.saldo);
    }
    return result;
  }

  async function loadMutasiForSelection() {
    const rekening = selectedRekening();
    const requestId = ++state.mutasiRequestId;
    state.auto = { saldoAwal: 0, sumber: "", saldoAkhirBank: null, mutasiRows: [], mutasiTruncated: false };

    if (!rekening || !state.monthKey) return;
    if (rekening.is_cash) {
      state.auto.sumber = "Kas tunai tidak punya mutasi bank — isi saldo awal secara manual.";
      return;
    }
    if (!state.mutasiAvailable) {
      state.auto.sumber = "Data mutasi bank tidak dapat diakses — isi saldo awal secara manual.";
      return;
    }

    const { start, end } = monthRange(state.monthKey);
    state.loadingMutasi = true;
    renderAll();
    try {
      // Ambil mutasi untuk setiap id rekening dalam grup (BRI = BritAma + BRImo).
      const perId = await Promise.all(
        rekening.ids.map(async (rekId) => {
          const params = new URLSearchParams({
            rekening_id: String(rekId),
            tanggal_mulai: start,
            tanggal_selesai: end,
            limit: String(MUTASI_ROWS_LIMIT),
          });
          const data = await getJson(`/mutasi/rows?${params.toString()}`, onUnauthorized);
          const rows = data.items || [];
          const truncated = rows.length >= MUTASI_ROWS_LIMIT;
          return { rekId, rows, truncated, ...saldoFromMutasi(rekId, rows, truncated, start, end) };
        })
      );
      if (requestId !== state.mutasiRequestId) return; // pilihan sudah berganti

      const withMutasi = perId.filter((p) => p.saldoAwal !== null || p.rows.length);
      const auto = {
        saldoAwal: 0,
        sumber: "",
        saldoAkhirBank: null,
        mutasiRows: perId.flatMap((p) => p.rows),
        mutasiTruncated: perId.some((p) => p.truncated),
      };

      const known = perId.filter((p) => p.saldoAwal !== null);
      if (known.length) {
        auto.saldoAwal = known.reduce((sum, p) => sum + p.saldoAwal, 0);
        const missing = perId.length - known.length;
        auto.sumber =
          `Otomatis dari ${known.map((p) => p.sumber).join(" + ")}.` +
          (missing ? ` ${missing} rekening lain dalam grup belum punya mutasi bulan ini.` : "");
      } else {
        auto.sumber = withMutasi.length
          ? "Saldo awal tidak bisa dihitung dari mutasi — isi secara manual."
          : "Belum ada mutasi bank bulan ini — isi saldo awal secara manual.";
      }

      const akhir = perId.filter((p) => p.saldoAkhir !== null);
      if (akhir.length && akhir.length === perId.filter((p) => p.rows.length || p.saldoAkhir !== null).length) {
        auto.saldoAkhirBank = akhir.reduce((sum, p) => sum + p.saldoAkhir, 0);
      }
      state.auto = auto;
    } catch (err) {
      if (requestId !== state.mutasiRequestId) return;
      if (err.status === 403) state.mutasiAvailable = false;
      state.auto.sumber = `Mutasi bank gagal dimuat (${err.message}) — isi saldo awal secara manual.`;
    } finally {
      if (requestId === state.mutasiRequestId) {
        state.loadingMutasi = false;
        renderAll();
      }
    }
  }

  /* ------------------------- Render ------------------------- */

  function renderAlert() {
    const messages = [];
    if (state.error) {
      messages.push({ cls: "bg-rose-50 border-rose-200 text-rose-700", text: state.error });
    }
    if (state.transactions.length >= RECENT_LIMIT) {
      messages.push({
        cls: "bg-amber-50 border-amber-200 text-amber-800",
        text: `Laporan dibentuk dari ${RECENT_LIMIT} transaksi Input Struk terakhir (batas maksimal API saat ini). Transaksi yang lebih lama mungkin belum ikut terhitung.`,
      });
    }
    if (state.auto.mutasiTruncated) {
      messages.push({
        cls: "bg-amber-50 border-amber-200 text-amber-800",
        text: `Mutasi bank bulan ini lebih dari ${MUTASI_ROWS_LIMIT} baris; ringkasan mutasi hanya memakai ${MUTASI_ROWS_LIMIT} baris terbaru.`,
      });
    }
    if (!messages.length) {
      el.alert.className = "hidden";
      el.alert.innerHTML = "";
      return;
    }
    el.alert.className = "space-y-2";
    el.alert.innerHTML = messages
      .map((m) => `<p class="rounded-xl border px-3 py-2 text-xs font-medium ${m.cls}">${esc(m.text)}</p>`)
      .join("");
  }

  function summaryCard(label, value, note = "", tone = "slate") {
    const tones = {
      slate: "text-slate-900",
      emerald: "text-emerald-700",
      rose: "text-rose-700",
      indigo: "text-indigo-700",
      amber: "text-amber-700",
    };
    return `
      <div class="rounded-2xl bg-white border border-slate-200/90 px-4 py-3 shadow-2xs min-w-0">
        <p class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 truncate">${esc(label)}</p>
        <p class="mt-1 text-base font-bold font-mono ${tones[tone] || tones.slate} truncate">${esc(value)}</p>
        ${note ? `<p class="mt-0.5 text-[11px] text-slate-500 leading-snug">${note}</p>` : ""}
      </div>`;
  }

  function renderSummary(report) {
    if (!report) {
      el.summary.innerHTML = "";
      return;
    }
    const cards = [
      summaryCard("Saldo Awal", formatRp(report.saldoAwal)),
      summaryCard("Total Debet (Masuk)", formatRp(report.totalDebetTransaksi), "", "emerald"),
      summaryCard("Total Kredit (Keluar)", formatRp(report.totalKredit), "", "rose"),
      summaryCard("Saldo Akhir (Catatan)", formatRp(report.saldoAkhir), "Saldo awal + debet − kredit", "indigo"),
    ];

    if (!report.rekening.is_cash) {
      const rows = state.auto.mutasiRows;
      const belumTercatat = rows.filter((r) => r.status_rekonsiliasi === "BELUM_TERCATAT").length;
      const belumRekon = rows.filter((r) => r.status_rekonsiliasi === "BELUM_REKON").length;
      const cocok = rows.length - belumTercatat - belumRekon;
      const txBelum = report.rows.filter((r) => !["SESUAI", "SELISIH_KODE_UNIK_ADMIN", "PINDAH_BUKU_COCOK"].includes(r.statusRekonsiliasi)).length;

      if (state.loadingMutasi) {
        cards.push(summaryCard("Mutasi Bank", "Memuat…", "", "slate"));
      } else if (state.auto.saldoAkhirBank !== null) {
        const selisih = report.saldoAkhir - state.auto.saldoAkhirBank;
        cards.push(
          summaryCard("Saldo Akhir Bank", formatRp(state.auto.saldoAkhirBank), "Dari mutasi bank bulan ini"),
          summaryCard(
            "Selisih Catatan vs Bank",
            formatRp(selisih),
            selisih === 0 ? "Saldo sudah cocok ✓" : "Periksa transaksi yang belum dicatat / belum rekon",
            selisih === 0 ? "emerald" : "amber"
          )
        );
      } else {
        cards.push(summaryCard("Saldo Akhir Bank", "-", "Belum ada mutasi bank bulan ini"));
      }
      cards.push(
        summaryCard(
          "Mutasi Bank",
          `${rows.length} baris`,
          `${cocok} cocok · ${belumTercatat} belum tercatat · ${belumRekon} belum rekon`
        ),
        summaryCard("Struk Belum Cocok", `${txBelum} transaksi`, "Struk yang belum ketemu pasangan mutasinya", txBelum ? "amber" : "emerald")
      );
    }
    el.summary.innerHTML = cards.join("");
  }

  function renderTable(report) {
    if (state.loading) {
      el.tbody.innerHTML = `<tr><td colspan="11" class="px-3 py-10 text-center text-slate-500">Memuat data…</td></tr>`;
      return;
    }
    if (!report) {
      el.tbody.innerHTML = `<tr><td colspan="11" class="px-3 py-10 text-center text-slate-500">Pilih rekening dan bulan.</td></tr>`;
      el.rowCount.textContent = "0 transaksi";
      return;
    }

    el.previewTitle.textContent = `${report.title} — ${monthLabel(report.monthKey)}`;
    el.previewSubtitle.textContent = `${report.company}${report.subtitle ? ` · ${report.subtitle}` : ""}`;
    el.rowCount.textContent = `${report.rows.length} transaksi`;

    const saldoAwalRow = `
      <tr class="bg-slate-50/70">
        <td class="px-3 py-2 text-slate-500">${esc(formatTanggalId(report.tanggalCetak))}</td>
        <td class="px-3 py-2 whitespace-nowrap">${esc(formatTanggalId(monthRange(report.monthKey).start))}</td>
        <td class="px-3 py-2 font-semibold">Saldo awal</td>
        <td class="px-3 py-2">Saldo Awal</td>
        <td class="px-3 py-2">${esc(report.rekening.kode_akun)}</td>
        <td class="px-3 py-2">${esc(report.rekening.kode_akun)}</td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.saldoAwal)}</td>
        <td class="px-3 py-2 text-right font-mono text-slate-400">-</td>
        <td class="px-3 py-2 text-right font-mono font-semibold">${formatRp(report.saldoAwal)}</td>
        <td class="px-3 py-2 text-slate-400">-</td>
        <td class="px-3 py-2"></td>
      </tr>`;

    const bodyRows = report.rows
      .map((row) => {
        const badge = TX_STATUS_BADGE[row.statusRekonsiliasi] || TX_STATUS_BADGE.BELUM_REKON;
        return `
          <tr class="hover:bg-slate-50/60 align-top">
            <td class="px-3 py-2 text-slate-500">${esc(row.tanggalInputAdmin)}</td>
            <td class="px-3 py-2 whitespace-nowrap">${esc(formatTanggalId(row.tanggal))}</td>
            <td class="px-3 py-2 text-slate-900 max-w-[320px]">${esc(row.keterangan)}</td>
            <td class="px-3 py-2">${esc(row.kategori)}</td>
            <td class="px-3 py-2">${esc(row.uangMasuk)}</td>
            <td class="px-3 py-2">${esc(row.uangKeluar)}</td>
            <td class="px-3 py-2 text-right font-mono text-emerald-700">${row.debet ? formatRp(row.debet) : "-"}</td>
            <td class="px-3 py-2 text-right font-mono text-rose-700">${row.kredit ? formatRp(row.kredit) : "-"}</td>
            <td class="px-3 py-2 text-right font-mono font-semibold">${formatRp(row.saldo)}</td>
            <td class="px-3 py-2 whitespace-nowrap ${row.jumlahLampiran ? "text-emerald-700" : "text-slate-500"}">${esc(row.lampiran)}${row.jumlahLampiran ? ` (${row.jumlahLampiran})` : ""}</td>
            <td class="px-3 py-2"><span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold whitespace-nowrap ${badge.cls}">${badge.label}</span></td>
          </tr>`;
      })
      .join("");

    const emptyRow = report.rows.length
      ? ""
      : `<tr><td colspan="11" class="px-3 py-8 text-center text-slate-500">Belum ada transaksi Input Struk untuk ${esc(report.rekening.kode_akun)} di ${esc(monthLabel(report.monthKey))}.</td></tr>`;

    const footer = `
      <tr class="bg-slate-50 font-bold border-t-2 border-slate-200">
        <td></td><td colspan="5" class="px-3 py-2">SUB TOTAL</td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.subTotalDebet)}</td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.totalKredit)}</td>
        <td colspan="3"></td>
      </tr>
      <tr class="bg-slate-50 font-bold">
        <td></td><td colspan="5" class="px-3 py-2">SISA SALDO</td>
        <td></td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.sisaSaldo)}</td>
        <td colspan="3"></td>
      </tr>
      <tr class="bg-slate-50 font-bold">
        <td></td><td colspan="5" class="px-3 py-2">GRAND TOTAL</td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.subTotalDebet)}</td>
        <td class="px-3 py-2 text-right font-mono">${formatRp(report.totalKredit + report.sisaSaldo)}</td>
        <td colspan="3"></td>
      </tr>`;

    el.tbody.innerHTML = saldoAwalRow + bodyRows + emptyRow + footer;
  }

  function renderSaldoInput() {
    const isManual = state.saldoAwalManual !== null;
    // Jangan menimpa input saat user sedang mengetik.
    if (document.activeElement !== el.saldo) {
      el.saldo.value = String(Math.round(effectiveSaldoAwal()));
    }
    el.resetSaldo.classList.toggle("hidden", !isManual);
    el.saldoHint.textContent = state.loadingMutasi
      ? "Mengambil saldo dari mutasi bank…"
      : isManual
        ? "Diisi manual."
        : state.auto.sumber || "";
  }

  function renderAll() {
    const busy = state.loading || state.downloading;
    el.refresh.disabled = busy;
    el.rekening.disabled = state.loading;
    el.month.disabled = state.loading;
    el.saldo.disabled = state.loading;
    el.download.disabled = busy || state.loadingMutasi || !selectedRekening() || !state.monthKey;
    el.downloadLabel.textContent = state.downloading ? "Menyiapkan…" : "Download Excel";

    renderAlert();
    renderSaldoInput();
    const report = state.loading ? null : currentReport();
    renderSummary(report);
    renderTable(report);
  }

  /* ------------------------- Load data ------------------------- */

  async function loadAll() {
    state.loading = true;
    state.error = "";
    renderAll();
    try {
      const [meta, recent, batches] = await Promise.all([
        getJson("/struk/metadata", onUnauthorized),
        getJson(`/struk/recent?limit=${RECENT_LIMIT}`, onUnauthorized),
        getJson("/mutasi/batches?limit=200", onUnauthorized).catch((err) => {
          if (err.status === 403) state.mutasiAvailable = false;
          return { items: [] };
        }),
      ]);
      state.rekening = buildRekeningOptions(meta.rekening_perusahaan || []);
      state.transactions = recent.items || [];
      state.batches = batches.items || [];

      if (!state.rekening.some((r) => String(r.id) === String(state.rekeningId))) {
        state.rekeningId = defaultRekeningId();
      }
      if (!state.monthKey) {
        state.monthKey = defaultMonthFor(selectedRekening());
      }
    } catch (err) {
      state.error = err.message || "Gagal memuat data rekonsiliasi.";
    } finally {
      state.loading = false;
      renderFilterOptions();
      renderAll();
    }
    await loadMutasiForSelection();
  }

  /* ------------------------- Events ------------------------- */

  el.rekening.addEventListener("change", async () => {
    state.rekeningId = el.rekening.value;
    state.saldoAwalManual = null;
    renderFilterOptions();
    renderAll();
    await loadMutasiForSelection();
  });

  el.month.addEventListener("change", async () => {
    state.monthKey = el.month.value;
    state.saldoAwalManual = null;
    renderAll();
    await loadMutasiForSelection();
  });

  el.saldo.addEventListener("input", () => {
    const raw = el.saldo.value.trim();
    state.saldoAwalManual = raw === "" ? 0 : Number(raw) || 0;
    renderAll();
  });

  el.resetSaldo.addEventListener("click", () => {
    state.saldoAwalManual = null;
    el.saldo.blur();
    renderAll();
  });

  el.refresh.addEventListener("click", () => loadAll());

  el.download.addEventListener("click", async () => {
    const report = currentReport();
    if (!report) return;
    state.downloading = true;
    state.error = "";
    renderAll();
    try {
      await downloadCashReport(report);
    } catch (err) {
      state.error = err.message || "Gagal membuat file Excel.";
    } finally {
      state.downloading = false;
      renderAll();
    }
  });

  // Muat library Excel di latar belakang supaya klik Download terasa cepat.
  loadExcelJS().catch(() => {});

  await loadAll();
}
