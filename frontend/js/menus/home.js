import { apiFetch } from "../api.js";

const BADGE_STYLE = {
  expense: {
    iconBox: "bg-rose-50 text-rose-600 ring-1 ring-rose-100",
    tagCls: "bg-rose-50 text-rose-700",
    barCls: "bg-rose-500",
    hoverRing: "hover:border-rose-200",
    shortGroup: "Pengeluaran",
    iconSvg: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 19L19 5M19 5H9M19 5v10" /></svg>`,
  },
  income: {
    iconBox: "bg-emerald-50 text-emerald-600 ring-1 ring-emerald-100",
    tagCls: "bg-emerald-50 text-emerald-700",
    barCls: "bg-emerald-500",
    hoverRing: "hover:border-emerald-200",
    shortGroup: "Pemasukan",
    iconSvg: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 5L5 19M5 19h10M5 19V9" /></svg>`,
  },
  transfer: {
    iconBox: "bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100",
    tagCls: "bg-indigo-50 text-indigo-700",
    barCls: "bg-indigo-500",
    hoverRing: "hover:border-indigo-200",
    shortGroup: "Pindah Buku",
    iconSvg: `<svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M7 16V4m0 0L3 8m4-4l4 4m6 0v12m0 0l4-4m-4 4l-4-4" /></svg>`,
  },
};

function renderWalletCard(ak, index) {
  const searchBlob = `${ak.nama_akun} ${ak.bank_lembaga} ${ak.no_rekening} ${ak.atas_nama}`.toLowerCase();
  const hasNorek = ak.no_rekening && ak.no_rekening !== "-";

  return `
    <article
      role="button"
      tabindex="0"
      data-search="${searchBlob}"
      data-card-index="${index}"
      class="account-card wallet-card group relative shrink-0 w-[84%] sm:w-[68%] md:w-auto snap-center rounded-[20px] bg-gradient-to-br ${ak.gradient} text-white p-5 min-h-[156px] flex flex-col justify-between shadow-md shadow-slate-900/15 ring-1 ring-white/15 cursor-pointer hover:-translate-y-0.5 hover:shadow-xl hover:shadow-slate-900/20 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-500/50 transition-all duration-200"
    >
      <div class="relative flex items-center justify-between gap-3">
        <h3 class="text-lg font-extrabold tracking-tight text-white truncate">${ak.nama_akun}</h3>
        <div class="w-8 h-6 rounded-md bg-gradient-to-br from-amber-200/90 via-amber-100/80 to-amber-300/80 border border-white/30 flex items-center justify-center shadow-inner shrink-0 opacity-90" aria-hidden="true">
          <div class="w-4 h-3.5 border border-amber-700/30 rounded-xs grid grid-cols-2">
            <span class="border-r border-amber-700/25"></span>
            <span></span>
          </div>
        </div>
      </div>

      <div class="relative space-y-1.5 pt-4">
        <div class="flex items-center justify-between gap-2">
          <span class="font-mono text-sm font-semibold tracking-wider text-white/95 truncate">${ak.no_rekening}</span>
          ${
            hasNorek
              ? `<button
                  type="button"
                  data-copy="${ak.no_rekening}"
                  aria-label="Salin nomor rekening ${ak.nama_akun}"
                  title="Salin nomor rekening"
                  class="copy-btn shrink-0 w-7 h-7 rounded-lg bg-white/10 hover:bg-white/25 text-white/90 inline-flex items-center justify-center transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                    <rect x="9" y="9" width="13" height="13" rx="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                </button>`
              : ""
          }
        </div>
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs font-medium tracking-wide text-white/75 truncate">${ak.atas_nama}</span>
          <svg class="w-3.5 h-3.5 text-white/50 group-hover:text-white group-hover:translate-x-0.5 transition shrink-0" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    </article>
  `;
}

function renderKategoriCard(kat) {
  const style = BADGE_STYLE[kat.badge] || BADGE_STYLE.transfer;
  const searchBlob = `${kat.nama} ${kat.kelompok}`.toLowerCase();
  const hasVal = kat.total_nominal > 0 || kat.jumlah_transaksi > 0;
  const paddedNo = String(kat.no).padStart(2, "0");

  return `
    <article
      class="kategori-row group bg-white rounded-2xl border border-slate-200/90 ${style.hoverRing} p-4 flex flex-col justify-between gap-3.5 shadow-2xs hover:shadow-md hover:-translate-y-0.5 transition-all duration-200"
      data-search="${searchBlob}"
      data-group="${kat.badge}"
    >
      <div class="flex items-start justify-between gap-2">
        <div class="flex items-center gap-2.5">
          <div class="w-10 h-10 rounded-xl ${style.iconBox} flex items-center justify-center shrink-0" aria-hidden="true">
            ${style.iconSvg}
          </div>
          <span class="font-mono text-xs font-semibold text-slate-400 tabular-nums">#${paddedNo}</span>
        </div>
        <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${style.tagCls}">
          ${style.shortGroup}
        </span>
      </div>

      <div>
        <h3 class="text-sm font-bold text-slate-900 leading-snug min-h-[2.4rem] flex items-start">${kat.nama}</h3>
      </div>

      <div class="pt-3 border-t border-slate-100">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-base font-extrabold tabular-nums ${hasVal ? "text-slate-900" : "text-slate-400"}">
            ${kat.total_nominal_fmt}
          </span>
          <span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-semibold tabular-nums ${kat.jumlah_transaksi > 0 ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-500"}">
            ${kat.jumlah_transaksi} tx
          </span>
        </div>
      </div>
    </article>
  `;
}

function renderRankingList(kategori, group = "all") {
  const filtered = kategori
    .filter((k) => (k.total_nominal || 0) > 0 && (group === "all" || k.badge === group))
    .sort((a, b) => (b.total_nominal || 0) - (a.total_nominal || 0));

  if (!filtered.length) {
    return `
      <div class="rounded-2xl border border-dashed border-slate-200 bg-slate-50/70 p-8 text-center">
        <p class="text-xs font-semibold text-slate-600">Belum ada transaksi pada kelompok ini.</p>
        <p class="text-[11px] text-slate-400 mt-1">Peringkat akan muncul otomatis setelah transaksi struk tersimpan.</p>
      </div>
    `;
  }

  const maxNominal = filtered[0].total_nominal || 0;
  const totalGroup = filtered.reduce((sum, item) => sum + (item.total_nominal || 0), 0);

  return `
    <div class="space-y-3">
      ${filtered
        .map((kat, idx) => {
          const style = BADGE_STYLE[kat.badge] || BADGE_STYLE.transfer;
          const widthPct = maxNominal > 0 ? Math.max(4, Math.round((kat.total_nominal / maxNominal) * 1000) / 10) : 0;
          const sharePct = totalGroup > 0 ? (Math.round((kat.total_nominal / totalGroup) * 1000) / 10).toFixed(1) : "0.0";
          const isTop = idx === 0;
          return `
            <div class="space-y-1.5">
              <div class="flex items-center justify-between gap-2 text-xs">
                <div class="flex items-center gap-2 min-w-0">
                  <span class="w-5 h-5 rounded-md text-[11px] font-bold tabular-nums inline-flex items-center justify-center shrink-0 ${
                    isTop ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600"
                  }">${idx + 1}</span>
                  <span class="font-semibold text-slate-800 truncate">${kat.nama}</span>
                  <span class="hidden sm:inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold shrink-0 ${style.tagCls}">
                    ${style.shortGroup}
                  </span>
                </div>
                <div class="flex items-center gap-2 shrink-0 tabular-nums">
                  <span class="text-[11px] text-slate-400">${sharePct}%</span>
                  <span class="font-bold text-slate-900">${kat.total_nominal_fmt}</span>
                </div>
              </div>
              <div class="h-2 w-full rounded-full bg-slate-100 overflow-hidden">
                <div class="h-full rounded-full ${style.barCls} transition-all duration-300" style="width: ${widthPct}%"></div>
              </div>
            </div>
          `;
        })
        .join("")}
    </div>
  `;
}

function renderComparisonCard(ringkasan) {
  const masuk = ringkasan.total_pemasukan || 0;
  const keluar = ringkasan.total_pengeluaran || 0;
  const totalArus = masuk + keluar;
  const maxVal = Math.max(masuk, keluar, 1);

  const masukPct = totalArus > 0 ? Math.round((masuk / totalArus) * 1000) / 10 : 0;
  const keluarPct = totalArus > 0 ? Math.round((100 - masukPct) * 10) / 10 : 0;
  const masukBarPct = masuk > 0 ? Math.max(6, Math.round((masuk / maxVal) * 1000) / 10) : 0;
  const keluarBarPct = keluar > 0 ? Math.max(6, Math.round((keluar / maxVal) * 1000) / 10) : 0;

  const radius = 52;
  const circumference = 2 * Math.PI * radius;
  const masukArc = totalArus > 0 ? (masuk / totalArus) * circumference : 0;
  const keluarArc = totalArus > 0 ? (keluar / totalArus) * circumference : 0;

  const selisih = ringkasan.selisih_bersih || 0;
  const isSurplus = selisih >= 0;
  const selisihSign = selisih > 0 ? "+" : "";

  return `
    <div class="bg-white rounded-3xl border border-slate-200/90 p-5 shadow-2xs flex flex-col justify-between gap-5">
      <div>
        <h3 class="text-sm font-bold text-slate-900 tracking-tight">Pemasukan vs Pengeluaran</h3>
        <p class="text-xs text-slate-500 mt-0.5">Komparasi total transaksi usaha masuk &amp; keluar.</p>
      </div>

      <div class="flex flex-col sm:flex-row lg:flex-col items-center gap-5">
        <div class="relative w-36 h-36 shrink-0 flex items-center justify-center">
          <svg class="w-full h-full -rotate-90" viewBox="0 0 140 140" aria-hidden="true">
            <circle cx="70" cy="70" r="${radius}" fill="none" stroke="#F1F5F9" stroke-width="18" />
            ${
              totalArus > 0
                ? `
                  <circle
                    cx="70" cy="70" r="${radius}" fill="none"
                    stroke="#F43F5E" stroke-width="18"
                    stroke-dasharray="${keluarArc.toFixed(2)} ${circumference.toFixed(2)}"
                    stroke-dashoffset="0"
                  />
                  <circle
                    cx="70" cy="70" r="${radius}" fill="none"
                    stroke="#10B981" stroke-width="18"
                    stroke-dasharray="${masukArc.toFixed(2)} ${circumference.toFixed(2)}"
                    stroke-dashoffset="${(-keluarArc).toFixed(2)}"
                  />
                `
                : ""
            }
          </svg>
          <div class="absolute inset-0 flex flex-col items-center justify-center text-center px-3">
            <span class="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Porsi</span>
            <span class="text-sm font-extrabold text-slate-900 tabular-nums mt-0.5">
              ${totalArus > 0 ? `${masukPct.toFixed(0)}% / ${keluarPct.toFixed(0)}%` : "0%"}
            </span>
          </div>
        </div>

        <div class="w-full space-y-3">
          <div class="space-y-1.5">
            <div class="flex items-center justify-between text-xs">
              <span class="inline-flex items-center gap-1.5 font-semibold text-slate-700">
                <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
                Pemasukan (${ringkasan.jumlah_pemasukan || 0} tx)
              </span>
              <span class="font-bold text-emerald-700 tabular-nums">${ringkasan.total_pemasukan_fmt || "Rp0"}</span>
            </div>
            <div class="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden">
              <div class="h-full rounded-full bg-emerald-500 transition-all duration-300" style="width: ${masukBarPct}%"></div>
            </div>
          </div>

          <div class="space-y-1.5">
            <div class="flex items-center justify-between text-xs">
              <span class="inline-flex items-center gap-1.5 font-semibold text-slate-700">
                <span class="w-2.5 h-2.5 rounded-full bg-rose-500"></span>
                Pengeluaran (${ringkasan.jumlah_pengeluaran || 0} tx)
              </span>
              <span class="font-bold text-rose-700 tabular-nums">${ringkasan.total_pengeluaran_fmt || "Rp0"}</span>
            </div>
            <div class="h-2.5 w-full rounded-full bg-slate-100 overflow-hidden">
              <div class="h-full rounded-full bg-rose-500 transition-all duration-300" style="width: ${keluarBarPct}%"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="pt-3.5 border-t border-slate-100 space-y-2">
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs font-semibold text-slate-600">Selisih Bersih</span>
          <span class="text-sm font-extrabold tabular-nums ${isSurplus ? "text-emerald-700" : "text-rose-700"}">
            ${selisihSign}${ringkasan.selisih_bersih_fmt || "Rp0"}
          </span>
        </div>
        <div class="flex items-center justify-between gap-2 text-[11px] text-slate-400">
          <span>Pindah Buku (non-usaha)</span>
          <span class="tabular-nums">${ringkasan.jumlah_pindah_buku || 0} tx • ${ringkasan.total_pindah_buku_fmt || "Rp0"}</span>
        </div>
      </div>
    </div>
  `;
}

export async function renderHomeMenu(container, { onUnauthorized }) {
  const res = await apiFetch("/home", {}, onUnauthorized);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || "Gagal memuat halaman Home");
  }

  const rekening = data.rekening || [];
  const kategori = data.kategori || [];
  const ringkasan = data.ringkasan || {};
  const expCount = kategori.filter((k) => k.badge === "expense").length;
  const incCount = kategori.filter((k) => k.badge === "income").length;
  const trfCount = kategori.filter((k) => k.badge === "transfer").length;

  const wrapper = document.createElement("div");
  wrapper.className = "space-y-8 view-animate";
  wrapper.innerHTML = `
    <!-- Search Bar -->
    <section aria-label="Pencarian">
      <div class="relative">
        <svg class="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input
          id="searchInput"
          type="text"
          autocomplete="off"
          placeholder="Cari nama bank, no. rekening, atau kategori SOP..."
          class="w-full h-11 pl-10 pr-16 rounded-2xl bg-white border border-slate-200/90 text-sm text-slate-900 placeholder-slate-400 shadow-xs focus:outline-none focus:ring-2 focus:ring-blue-600/30 focus:border-blue-600 transition"
        />
        <div class="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1">
          <button
            id="clearSearchBtn"
            type="button"
            aria-label="Hapus pencarian"
            class="hidden w-7 h-7 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 items-center justify-center transition"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <kbd id="searchHintKey" class="hidden sm:inline-flex items-center px-2 py-0.5 text-[11px] font-mono font-medium text-slate-400 bg-slate-100 border border-slate-200 rounded-md">/</kbd>
        </div>
      </div>
    </section>

    <!-- Section 1: Digital Wallet Cards -->
    <section id="sectionRekening" class="space-y-3.5">
      <div class="flex items-center justify-between gap-2">
        <div>
          <h2 class="text-base font-bold text-slate-900 tracking-tight">Kartu Rekening</h2>
          <p class="text-xs text-slate-500">Ketuk kartu untuk melihat Ringkasan Arus Kas &amp; rincian rekening.</p>
        </div>
        <button
          id="cardLayoutToggle"
          type="button"
          class="md:hidden inline-flex items-center gap-1.5 h-8 px-3 rounded-full text-xs font-semibold bg-white text-slate-700 border border-slate-200 shadow-xs active:scale-95 transition"
        >
          <span>⊞</span>
          <span id="cardLayoutText">Daftar</span>
        </button>
      </div>

      <div
        id="walletCardsTrack"
        class="flex md:grid md:grid-cols-2 gap-4 overflow-x-auto md:overflow-visible snap-x snap-mandatory no-scrollbar pb-2 md:pb-0 -mx-4 px-4 md:mx-0 md:px-0"
      >
        ${rekening.map((ak, i) => renderWalletCard(ak, i)).join("")}
      </div>

      <div id="carouselDots" class="flex md:hidden items-center justify-center gap-1.5 pt-1" aria-hidden="true">
        ${rekening
          .map(
            (_, i) =>
              `<span class="carousel-dot h-1.5 rounded-full transition-all duration-200 ${i === 0 ? "w-5 bg-slate-800" : "w-1.5 bg-slate-300"}"></span>`
          )
          .join("")}
      </div>
    </section>

    <!-- Section 2: Kantong Kategori SOP -->
    <section id="sectionKategori" class="space-y-4">
      <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 class="text-base font-bold text-slate-900 tracking-tight">Kantong Kategori SOP (${kategori.length})</h2>
          <p class="text-xs text-slate-500">Alokasi pemasukan, pengeluaran usaha, dan pindah buku antar rekening.</p>
        </div>

        <div class="flex items-center gap-1.5 overflow-x-auto no-scrollbar pb-0.5">
          <button type="button" data-cat-group="all" class="cat-filter-btn shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold bg-slate-900 text-white shadow-2xs transition">
            Semua (${kategori.length})
          </button>
          <button type="button" data-cat-group="expense" class="cat-filter-btn shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition">
            Pengeluaran (${expCount})
          </button>
          <button type="button" data-cat-group="income" class="cat-filter-btn shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition">
            Pemasukan (${incCount})
          </button>
          <button type="button" data-cat-group="transfer" class="cat-filter-btn shrink-0 h-8 px-3.5 rounded-full text-xs font-semibold bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition">
            Pindah Buku (${trfCount})
          </button>
        </div>
      </div>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
        ${kategori.map((kat) => renderKategoriCard(kat)).join("")}
      </div>
    </section>

    <!-- Section 3: Grafik Peringkat Kategori & Komparasi Pemasukan vs Pengeluaran -->
    <section id="sectionAnalytics" class="space-y-4">
      <div>
        <h2 class="text-base font-bold text-slate-900 tracking-tight">Ringkasan Grafik Transaksi</h2>
        <p class="text-xs text-slate-500">Peringkat kategori nominal terbesar dan komparasi pemasukan terhadap pengeluaran.</p>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-5 gap-4 items-start">
        <div class="lg:col-span-3 bg-white rounded-3xl border border-slate-200/90 p-5 shadow-2xs space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2.5">
            <div>
              <h3 class="text-sm font-bold text-slate-900 tracking-tight">Peringkat Kategori Terbesar</h3>
              <p class="text-xs text-slate-500 mt-0.5">Diurutkan dari nominal transaksi tertinggi ke terendah.</p>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <button type="button" data-rank-group="all" class="rank-filter-btn h-7 px-2.5 rounded-full text-[11px] font-semibold bg-slate-900 text-white transition">Semua</button>
              <button type="button" data-rank-group="expense" class="rank-filter-btn h-7 px-2.5 rounded-full text-[11px] font-semibold bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition">Pengeluaran</button>
              <button type="button" data-rank-group="income" class="rank-filter-btn h-7 px-2.5 rounded-full text-[11px] font-semibold bg-white text-slate-600 border border-slate-200 hover:bg-slate-50 transition">Pemasukan</button>
            </div>
          </div>

          <div id="rankingChartContainer">
            ${renderRankingList(kategori, "all")}
          </div>
        </div>

        <div class="lg:col-span-2">
          ${renderComparisonCard(ringkasan)}
        </div>
      </div>
    </section>

    <!-- Empty State -->
    <div id="emptyState" class="hidden rounded-3xl bg-white border border-slate-200 p-10 text-center space-y-3">
      <div class="w-12 h-12 rounded-2xl bg-slate-100 text-slate-500 mx-auto flex items-center justify-center">
        <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M21 21l-4.35-4.35m1.85-5.15a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
      </div>
      <div>
        <p class="text-sm font-semibold text-slate-900">Tidak ada hasil yang cocok</p>
        <p class="text-xs text-slate-500 mt-1">Coba kata kunci lain atau reset filter pencarian Anda.</p>
      </div>
      <button
        id="resetFilterBtn"
        type="button"
        class="inline-flex items-center justify-center h-9 px-4 rounded-xl text-xs font-semibold bg-slate-900 text-white hover:bg-slate-800 transition"
      >
        Reset Pencarian
      </button>
    </div>

    <!-- Card Detail Modal -->
    <div
      id="cardDetailModal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modalCardTitle"
      class="hidden fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4 bg-slate-950/55 backdrop-blur-xs"
    >
      <div class="modal-panel-animate w-full sm:max-w-lg bg-white rounded-t-3xl sm:rounded-3xl shadow-2xl border border-slate-200 overflow-hidden max-h-[90vh] flex flex-col">
        <div id="modalBanner" class="p-5 sm:p-6 bg-gradient-to-br from-slate-900 to-slate-800 text-white relative">
          <div class="flex items-start justify-between gap-3">
            <div>
              <p id="modalLembaga" class="text-xs font-medium text-white/80"></p>
              <h3 id="modalCardTitle" class="text-xl font-bold tracking-tight mt-0.5"></h3>
            </div>
            <button
              id="closeModalBtn"
              type="button"
              aria-label="Tutup rincian kartu"
              class="w-9 h-9 rounded-full bg-white/15 hover:bg-white/25 text-white flex items-center justify-center transition"
            >
              <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div class="mt-4 flex items-end justify-between gap-3">
            <div>
              <span class="text-[11px] text-white/75 block">Saldo Akhir Mutasi</span>
              <p id="modalSaldo" class="text-2xl font-extrabold tabular-nums mt-0.5"></p>
            </div>
            <span id="modalStatusPill" class="px-2.5 py-1 rounded-full text-xs font-semibold bg-white/15 border border-white/20"></span>
          </div>
        </div>

        <div class="p-5 sm:p-6 space-y-5 overflow-y-auto">
          <div class="rounded-2xl bg-slate-50 border border-slate-200/80 p-4 space-y-3">
            <div class="flex items-center justify-between gap-3">
              <div class="min-w-0">
                <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">Nomor Rekening</span>
                <span id="modalNorek" class="font-mono text-sm font-semibold text-slate-900 break-all"></span>
              </div>
              <button
                id="modalCopyBtn"
                type="button"
                class="shrink-0 h-9 px-3 rounded-xl bg-white border border-slate-200 text-xs font-semibold text-slate-700 hover:bg-slate-100 inline-flex items-center gap-1.5 shadow-2xs transition"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <rect x="9" y="9" width="13" height="13" rx="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                <span>Salin</span>
              </button>
            </div>
            <div class="pt-2.5 border-t border-slate-200/80">
              <span class="text-[11px] font-semibold uppercase tracking-wider text-slate-500 block">Atas Nama</span>
              <span id="modalAtasNama" class="text-sm font-semibold text-slate-900"></span>
            </div>
          </div>

          <div>
            <h4 class="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2.5">Ringkasan Arus Kas (Struk Internal)</h4>
            <div class="grid grid-cols-2 gap-2.5">
              <div class="rounded-2xl border border-slate-200 p-3">
                <span class="text-xs text-slate-500 block">Total Masuk</span>
                <span id="modalMasuk" class="mt-0.5 block text-sm font-bold text-emerald-700 tabular-nums"></span>
              </div>
              <div class="rounded-2xl border border-slate-200 p-3">
                <span class="text-xs text-slate-500 block">Total Keluar</span>
                <span id="modalKeluar" class="mt-0.5 block text-sm font-bold text-rose-700 tabular-nums"></span>
              </div>
              <div class="rounded-2xl border border-slate-200 p-3">
                <span class="text-xs text-slate-500 block">Pindah Buku</span>
                <span id="modalPindah" class="mt-0.5 block text-sm font-bold text-indigo-700 tabular-nums"></span>
              </div>
              <div class="rounded-2xl border border-slate-200 p-3">
                <span class="text-xs text-slate-500 block">Total Transaksi Struk</span>
                <span id="modalStruk" class="mt-0.5 block text-sm font-bold text-slate-900 tabular-nums"></span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div
      id="toast"
      role="status"
      aria-live="polite"
      class="pointer-events-none fixed bottom-20 md:bottom-6 left-1/2 -translate-x-1/2 z-[60] px-4 py-2.5 rounded-full bg-slate-900 text-white text-xs font-semibold shadow-lg opacity-0 translate-y-2 transition-all duration-200"
    ></div>
  `;

  container.replaceChildren(wrapper);

  // --- Interactivity ---
  const searchInput = wrapper.querySelector("#searchInput");
  const clearSearchBtn = wrapper.querySelector("#clearSearchBtn");
  const searchHintKey = wrapper.querySelector("#searchHintKey");
  const catFilterButtons = wrapper.querySelectorAll(".cat-filter-btn");
  const sectionRekening = wrapper.querySelector("#sectionRekening");
  const sectionKategori = wrapper.querySelector("#sectionKategori");
  const accountCards = wrapper.querySelectorAll(".account-card");
  const kategoriRows = wrapper.querySelectorAll(".kategori-row");
  const emptyState = wrapper.querySelector("#emptyState");
  const resetFilterBtn = wrapper.querySelector("#resetFilterBtn");

  const walletCardsTrack = wrapper.querySelector("#walletCardsTrack");
  const cardLayoutToggle = wrapper.querySelector("#cardLayoutToggle");
  const cardLayoutText = wrapper.querySelector("#cardLayoutText");
  const carouselDotsWrap = wrapper.querySelector("#carouselDots");
  const carouselDots = wrapper.querySelectorAll(".carousel-dot");

  const modal = wrapper.querySelector("#cardDetailModal");
  const modalBanner = wrapper.querySelector("#modalBanner");
  const closeModalBtn = wrapper.querySelector("#closeModalBtn");
  const modalCopyBtn = wrapper.querySelector("#modalCopyBtn");
  const toastEl = wrapper.querySelector("#toast");

  let activeCatGroup = "all";
  let isGridOnMobile = false;
  let toastTimer = null;
  let currentModalNorek = "";

  function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.remove("opacity-0", "translate-y-2");
    toastEl.classList.add("opacity-100", "translate-y-0");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.classList.add("opacity-0", "translate-y-2");
      toastEl.classList.remove("opacity-100", "translate-y-0");
    }, 2200);
  }

  async function copyText(text) {
    if (!text || text === "-") return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    showToast("Nomor rekening disalin: " + text);
  }

  function applyFilters() {
    const q = (searchInput.value || "").trim().toLowerCase();
    const hasQuery = q.length > 0;

    clearSearchBtn.classList.toggle("hidden", !hasQuery);
    clearSearchBtn.classList.toggle("inline-flex", hasQuery);
    searchHintKey.classList.toggle("sm:hidden", hasQuery);

    let visibleRek = 0;
    let visibleKat = 0;

    accountCards.forEach((card) => {
      const match = !q || card.dataset.search.includes(q);
      card.classList.toggle("hidden", !match);
      if (match) visibleRek++;
    });

    kategoriRows.forEach((row) => {
      const matchesQuery = !q || row.dataset.search.includes(q);
      const matchesGroup = activeCatGroup === "all" || row.dataset.group === activeCatGroup;
      const match = matchesQuery && matchesGroup;
      row.classList.toggle("hidden", !match);
      if (match) visibleKat++;
    });

    const showRek = visibleRek > 0;
    const showKat = visibleKat > 0;
    sectionRekening.classList.toggle("hidden", !showRek);
    sectionKategori.classList.toggle("hidden", !showKat);
    carouselDotsWrap.classList.toggle("hidden", isGridOnMobile || visibleRek <= 1);
    emptyState.classList.toggle("hidden", showRek || showKat);
  }

  function setCategoryGroup(group) {
    activeCatGroup = group;
    catFilterButtons.forEach((b) => {
      const active = b.dataset.catGroup === group;
      b.classList.toggle("bg-slate-900", active);
      b.classList.toggle("text-white", active);
      b.classList.toggle("shadow-2xs", active);
      b.classList.toggle("bg-white", !active);
      b.classList.toggle("text-slate-600", !active);
      b.classList.toggle("border", !active);
      b.classList.toggle("border-slate-200", !active);
    });
    applyFilters();
  }

  function openCardModal(ak) {
    modalBanner.className = `p-5 sm:p-6 bg-gradient-to-br text-white relative ${ak.gradient}`;
    wrapper.querySelector("#modalLembaga").textContent = ak.bank_lembaga;
    wrapper.querySelector("#modalCardTitle").textContent = ak.nama_akun;
    wrapper.querySelector("#modalSaldo").textContent = ak.saldo_akhir_fmt;
    wrapper.querySelector("#modalStatusPill").textContent = ak.has_mutasi
      ? `${ak.jumlah_mutasi} baris mutasi`
      : "Belum ada PDF mutasi";
    wrapper.querySelector("#modalNorek").textContent = ak.no_rekening;
    wrapper.querySelector("#modalAtasNama").textContent = ak.atas_nama;
    wrapper.querySelector("#modalMasuk").textContent = ak.masuk_fmt;
    wrapper.querySelector("#modalKeluar").textContent = ak.keluar_fmt;
    wrapper.querySelector("#modalPindah").textContent = ak.pindah_buku_fmt;
    wrapper.querySelector("#modalStruk").textContent = `${ak.jumlah_struk} transaksi`;

    currentModalNorek = ak.no_rekening;
    modalCopyBtn.classList.toggle("hidden", !currentModalNorek || currentModalNorek === "-");

    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
    closeModalBtn.focus();
  }

  function closeCardModal() {
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  catFilterButtons.forEach((btn) => {
    btn.addEventListener("click", () => setCategoryGroup(btn.dataset.catGroup));
  });

  const rankingChartContainer = wrapper.querySelector("#rankingChartContainer");
  const rankFilterButtons = wrapper.querySelectorAll(".rank-filter-btn");
  rankFilterButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.dataset.rankGroup;
      rankFilterButtons.forEach((b) => {
        const active = b.dataset.rankGroup === group;
        b.classList.toggle("bg-slate-900", active);
        b.classList.toggle("text-white", active);
        b.classList.toggle("bg-white", !active);
        b.classList.toggle("text-slate-600", !active);
        b.classList.toggle("border", !active);
        b.classList.toggle("border-slate-200", !active);
      });
      rankingChartContainer.innerHTML = renderRankingList(kategori, group);
    });
  });

  searchInput.addEventListener("input", applyFilters);
  clearSearchBtn.addEventListener("click", () => {
    searchInput.value = "";
    searchInput.focus();
    applyFilters();
  });
  resetFilterBtn.addEventListener("click", () => {
    searchInput.value = "";
    setCategoryGroup("all");
  });

  cardLayoutToggle.addEventListener("click", () => {
    isGridOnMobile = !isGridOnMobile;
    if (isGridOnMobile) {
      walletCardsTrack.classList.remove("flex", "overflow-x-auto", "snap-x", "snap-mandatory", "-mx-4", "px-4");
      walletCardsTrack.classList.add("grid", "grid-cols-1");
      accountCards.forEach((c) => c.classList.remove("w-[84%]", "sm:w-[68%]"));
      carouselDotsWrap.classList.add("hidden");
      cardLayoutText.textContent = "Geser";
    } else {
      walletCardsTrack.classList.add("flex", "overflow-x-auto", "snap-x", "snap-mandatory", "-mx-4", "px-4");
      walletCardsTrack.classList.remove("grid", "grid-cols-1");
      accountCards.forEach((c) => c.classList.add("w-[84%]", "sm:w-[68%]"));
      carouselDotsWrap.classList.remove("hidden");
      cardLayoutText.textContent = "Daftar";
    }
  });

  walletCardsTrack.addEventListener(
    "scroll",
    () => {
      if (isGridOnMobile || !carouselDots.length || !accountCards[0]) return;
      const step = accountCards[0].offsetWidth + 16;
      const idx = Math.round(walletCardsTrack.scrollLeft / step);
      carouselDots.forEach((dot, i) => {
        const active = i === idx;
        dot.classList.toggle("w-5", active);
        dot.classList.toggle("bg-slate-800", active);
        dot.classList.toggle("w-1.5", !active);
        dot.classList.toggle("bg-slate-300", !active);
      });
    },
    { passive: true }
  );

  wrapper.querySelectorAll(".copy-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      copyText(btn.dataset.copy);
    });
  });

  accountCards.forEach((card) => {
    const ak = rekening[Number(card.dataset.cardIndex)];
    card.addEventListener("click", () => openCardModal(ak));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        openCardModal(ak);
      }
    });
  });

  closeModalBtn.addEventListener("click", closeCardModal);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeCardModal();
  });
  modalCopyBtn.addEventListener("click", () => copyText(currentModalNorek));

  // Keyboard "/" & "Escape" (aktif hanya selama view Home masih terpasang di DOM)
  const onKeyDown = (e) => {
    if (!wrapper.isConnected) {
      document.removeEventListener("keydown", onKeyDown);
      return;
    }
    if (e.key === "/" && document.activeElement !== searchInput && modal.classList.contains("hidden")) {
      e.preventDefault();
      searchInput.focus();
    } else if (e.key === "Escape" && !modal.classList.contains("hidden")) {
      closeCardModal();
    }
  };
  document.addEventListener("keydown", onKeyDown);
}
