/**
 * Pembentuk data & file Excel "Cash Report" untuk menu Rekonsiliasi.
 *
 * Format mengikuti file "Cash_Report_Operasional-PT_Lokal_Komoditi_Indonesia_2026.xlsx"
 * (sheet "Template Cash Report Operasional"):
 *   - Baris 1-3 : Nama perusahaan, judul laporan, periode (merge B:I, bold, center)
 *   - Baris 5   : Header kolom A-J
 *   - Baris 6   : Saldo awal, lalu transaksi bulan terpilih
 *   - Footer    : SUB TOTAL, SISA SALDO, GRAND TOTAL, lalu kolom tanda tangan
 *
 * Modul ini murni frontend: data diambil dari endpoint yang sudah ada,
 * file .xlsx dibuat di browser dengan ExcelJS (dimuat dari CDN saat dibutuhkan).
 */

export const COMPANY_NAME = "PT Lokal Komoditi Indonesia";

export const BULAN_ID = [
  "Januari",
  "Februari",
  "Maret",
  "April",
  "Mei",
  "Juni",
  "Juli",
  "Agustus",
  "September",
  "Oktober",
  "November",
  "Desember",
];

export const HEADERS = [
  "TANGGAL INPUT DAN NAMA ADMIN",
  "TANGGAL TRANSAKSI",
  "KETERANGAN",
  "KATEGORI",
  "KETERANGAN UANG MASUK",
  "KETERANGAN UANG KELUAR",
  "DEBET",
  "KREDIT",
  "SALDO",
  "LAMPIRAN NOTA",
];

const COLUMN_WIDTHS = [26, 20.86, 70, 34.71, 25, 23.14, 19.57, 19.57, 19.57, 18.86];
const RP_FORMAT = '_-"Rp"* #,##0_-;\\-"Rp"* #,##0_-;_-"Rp"* "-"_-;_-@';
const DATE_FORMAT = "d-mmm-yy";
const EXCELJS_CDN = "https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js";

const HEADER_ROW = 5;
const FIRST_DATA_ROW = 6;

/* ------------------------------------------------------------------ */
/* Helper tanggal                                                       */
/* ------------------------------------------------------------------ */

/** "2026-01" -> { year: 2026, month: 1 } */
export function parseMonthKey(monthKey) {
  const [y, m] = String(monthKey || "").split("-").map(Number);
  return { year: y, month: m };
}

export function monthLabel(monthKey) {
  const { year, month } = parseMonthKey(monthKey);
  if (!year || !month) return "-";
  return `${BULAN_ID[month - 1]} ${year}`;
}

export function monthRange(monthKey) {
  const { year, month } = parseMonthKey(monthKey);
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const mm = String(month).padStart(2, "0");
  return {
    start: `${year}-${mm}-01`,
    end: `${year}-${mm}-${String(lastDay).padStart(2, "0")}`,
  };
}

/** "2026-01-05" -> "5 Januari 2026" */
export function formatTanggalId(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoDate || ""));
  if (!match) return String(isoDate || "");
  const [, y, m, d] = match;
  return `${Number(d)} ${BULAN_ID[Number(m) - 1]} ${y}`;
}

/** ISO date string -> Date UTC (agar serial Excel tidak bergeser zona waktu). */
function isoToUtcDate(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoDate || ""));
  if (!match) return null;
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

/* ------------------------------------------------------------------ */
/* Pemetaan transaksi internal -> baris Cash Report                     */
/* ------------------------------------------------------------------ */

function labelUangMasuk(tx) {
  const kategori = String(tx.nama_kategori || "");
  if (/penjualan|workshop|pendapatan usaha/i.test(kategori)) return "Masuk (Penjualan)";
  return "Masuk (Penerimaan)";
}

function buildKeterangan(tx) {
  const ket = String(tx.keterangan || "").trim();
  const pihak = String(tx.penerima_pengirim || "").trim();
  if (!ket) return pihak || "-";
  if (pihak && !ket.toLowerCase().includes(pihak.toLowerCase())) return `${ket} - ${pihak}`;
  return ket;
}

/**
 * Mengubah satu transaksi internal menjadi baris laporan untuk rekening tertentu.
 * Mengembalikan null jika transaksi tidak menyentuh rekening tersebut.
 *
 * Aturan (sama dengan logika rekonsiliasi di backend):
 *   - MASUK       : uang masuk ke rekening_sumber            -> DEBET total_mutasi
 *   - KELUAR      : uang keluar dari rekening_sumber         -> KREDIT total_mutasi
 *   - PINDAH_BUKU : keluar dari sumber sebesar total_mutasi  -> KREDIT
 *                   masuk ke tujuan sebesar nominal_pokok    -> DEBET
 */
export function mapTransactionToRow(tx, rekening) {
  // Satu pilihan rekening bisa mewakili beberapa id (mis. BRI BritAma + BRI BRImo digabung jadi "BRI").
  const ids = new Set((rekening.ids && rekening.ids.length ? rekening.ids : [rekening.id]).map(Number));
  const kode = rekening.kode_akun;
  const sumberIn = ids.has(Number(tx.rekening_sumber_id));
  const tujuanIn = tx.rekening_tujuan_id != null && ids.has(Number(tx.rekening_tujuan_id));
  const total = Number(tx.total_mutasi || 0);
  const pokok = Number(tx.nominal_pokok || 0);
  const masukPindahBuku = pokok > 0 ? pokok : total;

  let uangMasuk = "";
  let uangKeluar = "";
  let debet = 0;
  let kredit = 0;

  if (tx.tipe === "MASUK" && sumberIn) {
    uangMasuk = labelUangMasuk(tx);
    uangKeluar = kode;
    debet = total;
  } else if (tx.tipe === "KELUAR" && sumberIn) {
    uangMasuk = kode;
    uangKeluar = "Keluar (Pembayaran)";
    kredit = total;
  } else if (tx.tipe === "PINDAH_BUKU" && sumberIn && tujuanIn) {
    // Pindah buku antar rekening dalam grup yang sama: masuk & keluar sekaligus (bersih = biaya admin).
    uangMasuk = tx.rekening_sumber || kode;
    uangKeluar = tx.rekening_tujuan || kode;
    debet = masukPindahBuku;
    kredit = total;
  } else if (tx.tipe === "PINDAH_BUKU" && sumberIn) {
    uangMasuk = tx.rekening_sumber || kode;
    uangKeluar = tx.rekening_tujuan || "-";
    kredit = total;
  } else if (tx.tipe === "PINDAH_BUKU" && tujuanIn) {
    uangMasuk = tx.rekening_sumber || "-";
    uangKeluar = tx.rekening_tujuan || kode;
    debet = masukPindahBuku;
  } else {
    return null;
  }

  const files = Array.isArray(tx.files) ? tx.files : [];
  const adminParts = [formatTanggalId(tx.tanggal_input), String(tx.nama_admin || "").trim()].filter(Boolean);

  return {
    id: tx.id,
    tanggalInputAdmin: adminParts.join(" - "),
    tanggal: tx.tanggal_transaksi,
    waktu: tx.waktu_transaksi || "",
    keterangan: buildKeterangan(tx),
    kategori: tx.nama_kategori || "-",
    uangMasuk,
    uangKeluar,
    debet,
    kredit,
    lampiran: files.length ? "Terlampir" : "Belum Terlampir",
    jumlahLampiran: files.length,
    statusRekonsiliasi: tx.status_rekonsiliasi || "BELUM_REKON",
  };
}

/**
 * Menyusun model laporan lengkap (baris + saldo berjalan + total) untuk satu rekening & bulan.
 */
export function buildCashReport({ transactions, rekening, monthKey, saldoAwal = 0, tanggalCetak = null }) {
  const { start, end } = monthRange(monthKey);

  const rows = (transactions || [])
    .filter((tx) => tx.tanggal_transaksi >= start && tx.tanggal_transaksi <= end)
    .map((tx) => mapTransactionToRow(tx, rekening))
    .filter(Boolean)
    .sort(
      (a, b) =>
        a.tanggal.localeCompare(b.tanggal) ||
        String(a.waktu).localeCompare(String(b.waktu)) ||
        Number(a.id) - Number(b.id)
    );

  const awal = Number(saldoAwal) || 0;
  let saldo = awal;
  for (const row of rows) {
    saldo = saldo + row.debet - row.kredit;
    row.saldo = saldo;
  }

  const totalDebetTransaksi = rows.reduce((sum, r) => sum + r.debet, 0);
  const totalKredit = rows.reduce((sum, r) => sum + r.kredit, 0);
  const subTotalDebet = awal + totalDebetTransaksi; // sama dengan rumus SUM(G..) di Excel (termasuk saldo awal)
  const sisaSaldo = subTotalDebet - totalKredit;

  const today = new Date();
  const cetakIso =
    tanggalCetak ||
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  return {
    company: COMPANY_NAME,
    title: rekening.is_cash ? "Cash Report Operasional" : `Cash Report ${rekening.kode_akun}`,
    subtitle: rekening.is_cash ? "" : [rekening.bank_lembaga, rekening.no_rekening].filter(Boolean).join(" - "),
    periode: `Periode ${monthLabel(monthKey)}`,
    monthKey,
    rekening,
    tanggalCetak: cetakIso,
    saldoAwal: awal,
    rows,
    totalDebetTransaksi,
    totalKredit,
    subTotalDebet,
    sisaSaldo,
    saldoAkhir: saldo,
  };
}

/* ------------------------------------------------------------------ */
/* Penulisan workbook (ExcelJS)                                         */
/* ------------------------------------------------------------------ */

export function sheetNameFor(report) {
  const { month } = parseMonthKey(report.monthKey);
  const raw = `${report.rekening.is_cash ? "Cash Report Operasional" : `Cash Report ${report.rekening.kode_akun}`}-${BULAN_ID[month - 1]}`;
  return raw.replace(/[\\/?*[\]:]/g, " ").slice(0, 31);
}

export function fileNameFor(report) {
  const { year, month } = parseMonthKey(report.monthKey);
  const akun = String(report.rekening.kode_akun || "Rekening").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "");
  return `Cash_Report_${akun}-${BULAN_ID[month - 1]}_${year}-PT_Lokal_Komoditi_Indonesia.xlsx`;
}

const THIN = { style: "thin" };
const BORDER_ALL = { top: THIN, left: THIN, bottom: THIN, right: THIN };
const FONT = { name: "Calibri", size: 11 };

/**
 * Mengisi satu worksheet sesuai format template. `ExcelJS` tidak dibutuhkan di sini,
 * cukup objek workbook yang sudah dibuat.
 */
export function addCashReportSheet(workbook, report) {
  const ws = workbook.addWorksheet(sheetNameFor(report), {
    views: [{ state: "frozen", xSplit: 0, ySplit: HEADER_ROW, topLeftCell: `A${FIRST_DATA_ROW}` }],
    pageSetup: { orientation: "landscape", paperSize: 9, fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  });

  COLUMN_WIDTHS.forEach((width, idx) => {
    ws.getColumn(idx + 1).width = width;
  });

  // Baris 1-3: judul (merge B:I)
  const titleLines = [
    report.company,
    report.subtitle ? `${report.title} (${report.subtitle})` : report.title,
    report.periode,
  ];
  titleLines.forEach((text, idx) => {
    const r = idx + 1;
    ws.mergeCells(`B${r}:I${r}`);
    const cell = ws.getCell(`B${r}`);
    cell.value = text;
    cell.font = { ...FONT, size: 14, bold: true };
    cell.alignment = { horizontal: "center" };
    ws.getRow(r).height = 19.5;
  });

  // Baris 5: header
  const header = ws.getRow(HEADER_ROW);
  header.height = 32;
  HEADERS.forEach((text, idx) => {
    const cell = header.getCell(idx + 1);
    cell.value = text;
    cell.font = { ...FONT, bold: true };
    cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
    cell.border = BORDER_ALL;
  });

  const styleDataRow = (row) => {
    for (let c = 1; c <= 10; c += 1) {
      const cell = row.getCell(c);
      cell.font = FONT;
      cell.border = BORDER_ALL;
      if (c === 1 || c === 2) cell.alignment = { horizontal: "left", vertical: "top" };
      if (c === 2) cell.numFmt = DATE_FORMAT;
      if (c >= 7 && c <= 9) cell.numFmt = RP_FORMAT;
      if (c === 3) cell.alignment = { vertical: "top", wrapText: true };
    }
  };

  // Baris saldo awal
  let r = FIRST_DATA_ROW;
  const saldoRow = ws.getRow(r);
  saldoRow.values = [
    formatTanggalId(report.tanggalCetak),
    isoToUtcDate(monthRange(report.monthKey).start),
    "Saldo awal",
    "Saldo Awal",
    report.rekening.kode_akun,
    report.rekening.kode_akun,
    report.saldoAwal,
    null,
    { formula: `G${r}`, result: report.saldoAwal },
    "-",
  ];
  styleDataRow(saldoRow);

  // Baris transaksi
  for (const item of report.rows) {
    r += 1;
    const row = ws.getRow(r);
    row.values = [
      item.tanggalInputAdmin,
      isoToUtcDate(item.tanggal),
      item.keterangan,
      item.kategori,
      item.uangMasuk,
      item.uangKeluar,
      item.debet || null,
      item.kredit || null,
      { formula: `I${r - 1}+G${r}-H${r}`, result: item.saldo },
      item.lampiran,
    ];
    styleDataRow(row);
  }
  const lastDataRow = r;

  ws.autoFilter = { from: `A${HEADER_ROW}`, to: `J${lastDataRow}` };

  // Footer: SUB TOTAL, SISA SALDO, GRAND TOTAL
  const subRow = lastDataRow + 1;
  const sisaRow = subRow + 1;
  const grandRow = sisaRow + 1;
  const footer = [
    {
      row: subRow,
      label: "SUB TOTAL",
      G: { formula: `SUM(G${FIRST_DATA_ROW}:G${lastDataRow})`, result: report.subTotalDebet },
      H: { formula: `SUM(H${FIRST_DATA_ROW}:H${lastDataRow})`, result: report.totalKredit },
    },
    {
      row: sisaRow,
      label: "SISA SALDO",
      G: null,
      H: { formula: `G${subRow}-H${subRow}`, result: report.sisaSaldo },
    },
    {
      row: grandRow,
      label: "GRAND TOTAL",
      G: { formula: `G${subRow}+G${sisaRow}`, result: report.subTotalDebet },
      H: { formula: `H${subRow}+H${sisaRow}`, result: report.totalKredit + report.sisaSaldo },
    },
  ];
  for (const f of footer) {
    const row = ws.getRow(f.row);
    for (let c = 1; c <= 10; c += 1) {
      const cell = row.getCell(c);
      cell.font = { ...FONT, bold: true };
      cell.border = BORDER_ALL;
      if (c >= 4 && c <= 9) cell.numFmt = RP_FORMAT;
    }
    ws.mergeCells(`B${f.row}:C${f.row}`);
    row.getCell(2).value = f.label;
    if (f.G) row.getCell(7).value = f.G;
    if (f.H) row.getCell(8).value = f.H;
  }

  // Tanda tangan
  const signRow = grandRow + 3;
  ws.getCell(`B${signRow}`).value = "Disetujui Oleh,";
  ws.getCell(`H${signRow}`).value = "Disusun Oleh,";
  ws.getCell(`B${signRow + 4}`).value = "(..............................)";
  ws.getCell(`H${signRow + 4}`).value = "(..............................)";
  [`B${signRow}`, `H${signRow}`, `B${signRow + 4}`, `H${signRow + 4}`].forEach((addr) => {
    ws.getCell(addr).font = FONT;
  });

  return ws;
}

export function createCashReportWorkbook(ExcelJS, report) {
  const workbook = new ExcelJS.Workbook();
  workbook.creator = COMPANY_NAME;
  workbook.created = new Date();
  addCashReportSheet(workbook, report);
  return workbook;
}

/* ------------------------------------------------------------------ */
/* Browser: muat ExcelJS & unduh file                                   */
/* ------------------------------------------------------------------ */

let excelJsPromise = null;

export function loadExcelJS() {
  if (typeof window !== "undefined" && window.ExcelJS) return Promise.resolve(window.ExcelJS);
  if (!excelJsPromise) {
    excelJsPromise = new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = EXCELJS_CDN;
      script.async = true;
      script.onload = () =>
        window.ExcelJS ? resolve(window.ExcelJS) : reject(new Error("Library Excel gagal dimuat"));
      script.onerror = () => {
        excelJsPromise = null;
        script.remove();
        reject(new Error("Library Excel gagal dimuat. Periksa koneksi internet."));
      };
      document.head.appendChild(script);
    });
  }
  return excelJsPromise;
}

export async function downloadCashReport(report) {
  const ExcelJS = await loadExcelJS();
  const workbook = createCashReportWorkbook(ExcelJS, report);
  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileNameFor(report);
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
