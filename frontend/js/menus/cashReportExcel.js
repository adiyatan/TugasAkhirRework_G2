/**
 * Pembentuk data & file Excel "Cash Report" (helper JS).
 *
 * Format mengikuti struktur Cash Report Operasional PT Lokal Komoditi Indonesia:
 *   - Baris 1-3 : Nama perusahaan, judul laporan, periode (merge B:I, bold, center)
 *   - Baris 5   : Header kolom A-J
 *   - Baris 6   : Saldo awal, lalu transaksi bulan terpilih
 *   - Footer    : SUB TOTAL, SISA SALDO, GRAND TOTAL, lalu kolom tanda tangan
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

const COLUMN_WIDTHS = [28, 18, 56, 36, 22, 22, 20, 20, 20, 28];
const RP_FORMAT_INT = '_-"Rp"* #,##0_-;\\-"Rp"* #,##0_-;_-"Rp"* "-"_-;_-@';
const RP_FORMAT_DEC = '_-"Rp"* #,##0.00_-;\\-"Rp"* #,##0.00_-;_-"Rp"* "-"_-;_-@';
const DATE_FORMAT = "d-mmm-yy";
const EXCELJS_CDN = "https://cdn.jsdelivr.net/npm/exceljs@4.4.0/dist/exceljs.min.js";

const HEADER_ROW = 5;
const FIRST_DATA_ROW = 6;

export function round2(value) {
  const n = Math.round(Number(value || 0) * 100) / 100;
  return Object.is(n, -0) || Math.abs(n) < 0.005 ? 0 : n;
}

/* ------------------------------------------------------------------ */
/* Helper tanggal                                                       */
/* ------------------------------------------------------------------ */

/** "2026-01" -> { year: 2026, month: 1 } (atau null jika tidak valid) */
export function parseMonthKey(monthKey) {
  const match = /^(\d{4})-(\d{2})$/.exec(String(monthKey || "").trim());
  if (!match) return { year: NaN, month: NaN };
  const year = Number(match[1]);
  const month = Number(match[2]);
  if (month < 1 || month > 12) return { year: NaN, month: NaN };
  return { year, month };
}

export function monthLabel(monthKey) {
  const { year, month } = parseMonthKey(monthKey);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) return "-";
  return `${BULAN_ID[month - 1]} ${year}`;
}

export function monthRange(monthKey) {
  const { year, month } = parseMonthKey(monthKey);
  if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) {
    return { start: "", end: "" };
  }
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
  const m = Number(match[2]);
  if (m < 1 || m > 12) return String(isoDate || "");
  return `${Number(match[3])} ${BULAN_ID[m - 1]} ${match[1]}`;
}

/** ISO date string -> Date UTC (agar serial Excel tidak bergeser zona waktu). */
function isoToUtcDate(isoDate) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(isoDate || ""));
  if (!match) return null;
  const m = Number(match[2]);
  if (m < 1 || m > 12) return null;
  return new Date(Date.UTC(Number(match[1]), m - 1, Number(match[3])));
}

/* ------------------------------------------------------------------ */
/* Pemetaan transaksi internal -> baris Cash Report                     */
/* ------------------------------------------------------------------ */

function buildKeterangan(tx) {
  const ket = String(tx.keterangan || "").trim();
  const pihak = String(tx.penerima_pengirim || "").trim();
  if (!ket) return pihak || "-";
  if (pihak && !ket.toLowerCase().includes(pihak.toLowerCase())) return `${ket} - ${pihak}`;
  return ket;
}

/**
 * Mengubah satu transaksi internal menjadi baris laporan untuk satu rekening.
 * Mengikuti aturan REQUIREMENT_INPUT_STRUK.md & cash_report_mapper.py:
 *   - MASUK       : DEBET total_mutasi; Uang Masuk = rekening_sumber, Uang Keluar = ""
 *   - KELUAR      : KREDIT total_mutasi; Uang Masuk = "", Uang Keluar = rekening_sumber
 *   - PINDAH_BUKU : sisi sumber -> KREDIT total_mutasi; sisi tujuan -> DEBET nominal_pokok;
 *                   Uang Masuk = rekening_tujuan, Uang Keluar = rekening_sumber
 */
export function mapTransactionToRow(tx, rekening) {
  const rekId = Number(rekening.id);
  const kode = rekening.kode_akun || "";
  const sumberMatch = Number(tx.rekening_sumber_id) === rekId;
  const tujuanMatch = tx.rekening_tujuan_id != null && Number(tx.rekening_tujuan_id) === rekId;
  const total = round2(tx.total_mutasi || 0);
  const pokok = round2(tx.nominal_pokok || 0);
  const masukPindahBuku = pokok > 0 ? pokok : total;

  let uangMasuk = "";
  let uangKeluar = "";
  let debet = 0;
  let kredit = 0;

  if (tx.tipe === "MASUK" && sumberMatch) {
    uangMasuk = tx.rekening_sumber || kode;
    uangKeluar = "";
    debet = total;
  } else if (tx.tipe === "KELUAR" && sumberMatch) {
    uangMasuk = "";
    uangKeluar = tx.rekening_sumber || kode;
    kredit = total;
  } else if (tx.tipe === "PINDAH_BUKU" && sumberMatch) {
    uangMasuk = tx.rekening_tujuan || "";
    uangKeluar = tx.rekening_sumber || kode;
    kredit = total;
  } else if (tx.tipe === "PINDAH_BUKU" && tujuanMatch) {
    uangMasuk = tx.rekening_tujuan || kode;
    uangKeluar = tx.rekening_sumber || "";
    debet = masukPindahBuku;
  } else {
    return null;
  }

  const files = Array.isArray(tx.files) ? tx.files : [];
  const adminParts = [formatTanggalId(tx.tanggal_input), String(tx.nama_admin || "").trim()].filter(Boolean);
  let lampiran = "Belum Terlampir";
  if (files.length) {
    const names = files.map((f) => f.orig_filename || f.filename).filter(Boolean).join(", ");
    lampiran = names ? `Terlampir (${names})` : "Terlampir";
  } else if (tx.sumber_pencatatan === "PENYESUAIAN_MUTASI") {
    lampiran = "Penyesuaian Mutasi";
  }

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
    lampiran,
    files,
    jumlahLampiran: files.length,
    statusRekonsiliasi: tx.status_rekonsiliasi || "BELUM_REKON",
  };
}

/**
 * Menyusun model laporan lengkap (baris + saldo berjalan + total) untuk satu rekening & bulan.
 */
export function buildCashReport({ transactions, rekening, monthKey, saldoAwal = 0, tanggalCetak = null }) {
  const { start, end } = monthRange(monthKey);
  if (!start || !end) {
    throw new Error(`Bulan tidak valid: ${monthKey}`);
  }

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

  const awal = round2(saldoAwal);
  let saldo = awal;
  for (const row of rows) {
    saldo = round2(saldo + row.debet - row.kredit);
    row.saldo = saldo;
  }

  const totalDebetTransaksi = round2(rows.reduce((sum, r) => sum + r.debet, 0));
  const totalKredit = round2(rows.reduce((sum, r) => sum + r.kredit, 0));
  const subTotalDebet = round2(awal + totalDebetTransaksi);
  const sisaSaldo = round2(subTotalDebet - totalKredit);

  const today = new Date();
  const cetakIso =
    tanggalCetak ||
    `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;

  return {
    company: COMPANY_NAME,
    title: rekening.is_cash ? "Cash Report Operasional" : `Cash Report ${rekening.kode_akun}`,
    subtitle: rekening.is_cash
      ? ""
      : [rekening.bank_lembaga, rekening.no_rekening].filter((v) => v && v !== "-").join(" - "),
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
  const bulan = Number.isInteger(month) && month >= 1 && month <= 12 ? BULAN_ID[month - 1] : "Laporan";
  const raw = `${report.rekening.is_cash ? "Cash Report Operasional" : `Cash Report ${report.rekening.kode_akun}`}-${bulan}`;
  return (raw.replace(/[\\/?*[\]:]/g, " ").trim().replace(/^'+|'+$/g, "").slice(0, 31).trim() || "Cash Report");
}

export function fileNameFor(report) {
  const { year, month } = parseMonthKey(report.monthKey);
  const akun = String(report.rekening.kode_akun || "Rekening").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "Rekening";
  const bulan = Number.isInteger(month) && month >= 1 && month <= 12 ? BULAN_ID[month - 1] : "Bulan";
  const tahun = Number.isInteger(year) ? year : "0000";
  return `Cash_Report_${akun}-${bulan}_${tahun}-PT_Lokal_Komoditi_Indonesia.xlsx`;
}

const THIN = { style: "thin" };
const BORDER_ALL = { top: THIN, left: THIN, bottom: THIN, right: THIN };
const FONT = { name: "Calibri", size: 11 };

function hasCents(values) {
  return values.some((v) => v !== null && v !== undefined && Math.abs(Number(v) - Math.round(Number(v))) > 1e-6);
}

/**
 * Mengisi satu worksheet sesuai format Cash Report.
 */
export function addCashReportSheet(workbook, report) {
  const ws = workbook.addWorksheet(sheetNameFor(report), {
    views: [{ state: "frozen", xSplit: 0, ySplit: HEADER_ROW, topLeftCell: `A${FIRST_DATA_ROW}` }],
    pageSetup: { orientation: "landscape", paperSize: 9, fitToPage: true, fitToWidth: 1, fitToHeight: 0 },
  });

  COLUMN_WIDTHS.forEach((width, idx) => {
    ws.getColumn(idx + 1).width = width;
  });

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
    cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
    ws.getRow(r).height = text.length > 80 ? 36 : 24;
  });

  const header = ws.getRow(HEADER_ROW);
  header.height = 32;
  HEADERS.forEach((text, idx) => {
    const cell = header.getCell(idx + 1);
    cell.value = text;
    cell.font = { ...FONT, bold: true };
    cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
    cell.border = BORDER_ALL;
  });

  const rpFormat = hasCents([
    report.saldoAwal,
    report.subTotalDebet,
    report.totalKredit,
    report.sisaSaldo,
    report.saldoAkhir,
    ...report.rows.flatMap((row) => [row.debet, row.kredit, row.saldo]),
  ])
    ? RP_FORMAT_DEC
    : RP_FORMAT_INT;

  const styleDataRow = (row) => {
    for (let c = 1; c <= 10; c += 1) {
      const cell = row.getCell(c);
      cell.font = FONT;
      cell.border = BORDER_ALL;
      if (c === 2) {
        cell.alignment = { horizontal: "left", vertical: "top" };
        cell.numFmt = DATE_FORMAT;
      } else if (c >= 7 && c <= 9) {
        cell.alignment = { horizontal: "right", vertical: "top" };
        cell.numFmt = rpFormat;
      } else {
        cell.alignment = { horizontal: "left", vertical: "top", wrapText: true };
      }
    }
  };

  let r = FIRST_DATA_ROW;
  const saldoRow = ws.getRow(r);
  saldoRow.values = [
    null,
    isoToUtcDate(monthRange(report.monthKey).start),
    "Saldo Awal",
    "Saldo Awal",
    null,
    null,
    report.saldoAwal,
    null,
    { formula: `G${r}`, result: report.saldoAwal },
    "-",
  ];
  styleDataRow(saldoRow);

  for (const item of report.rows) {
    r += 1;
    const row = ws.getRow(r);
    row.values = [
      item.tanggalInputAdmin,
      isoToUtcDate(item.tanggal),
      item.keterangan,
      item.kategori,
      item.uangMasuk || null,
      item.uangKeluar || null,
      item.debet || null,
      item.kredit || null,
      { formula: `I${r - 1}+G${r}-H${r}`, result: item.saldo },
      item.lampiran,
    ];
    styleDataRow(row);
  }
  const lastDataRow = r;

  ws.autoFilter = { from: `A${HEADER_ROW}`, to: `J${lastDataRow}` };

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
      G: { formula: `G${subRow}`, result: report.subTotalDebet },
      H: { formula: `H${subRow}+H${sisaRow}`, result: round2(report.totalKredit + report.sisaSaldo) },
    },
  ];
  for (const f of footer) {
    const row = ws.getRow(f.row);
    for (let c = 1; c <= 10; c += 1) {
      const cell = row.getCell(c);
      cell.font = { ...FONT, bold: true };
      cell.border = BORDER_ALL;
      if (c >= 7 && c <= 9) cell.numFmt = rpFormat;
    }
    ws.mergeCells(`B${f.row}:C${f.row}`);
    row.getCell(2).value = f.label;
    if (f.G) row.getCell(7).value = f.G;
    if (f.H) row.getCell(8).value = f.H;
  }

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
      script.onload = () => {
        if (window.ExcelJS) {
          resolve(window.ExcelJS);
          return;
        }
        excelJsPromise = null;
        script.remove();
        reject(new Error("Library Excel gagal dimuat"));
      };
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
