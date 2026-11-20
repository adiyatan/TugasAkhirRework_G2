from datetime import date
from decimal import Decimal
from io import BytesIO
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side

from app.schemas.bank_statement import CashReportRow

_SS_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _inject_cached_formula_values(
    xlsx_bytes: bytes,
    cached_values: dict[str, int | float],
    sheet_path: str = "xl/worksheets/sheet1.xml",
) -> bytes:
    """Populate cached <v> results on formula cells so Excel Protected View and previews display values."""
    if not cached_values:
        return xlsx_bytes

    ET.register_namespace("", _SS_NS)
    ET.register_namespace("r", _R_NS)

    out_buf = BytesIO()
    with zipfile.ZipFile(BytesIO(xlsx_bytes), "r") as zin, zipfile.ZipFile(
        out_buf, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for info in zin.infolist():
            raw = zin.read(info.filename)
            if info.filename == sheet_path:
                root = ET.fromstring(raw)
                f_tag = f"{{{_SS_NS}}}f"
                v_tag = f"{{{_SS_NS}}}v"
                for cell in root.iter(f"{{{_SS_NS}}}c"):
                    coord = cell.attrib.get("r")
                    if coord not in cached_values:
                        continue
                    if cell.find(f_tag) is None:
                        continue
                    cell.attrib.pop("t", None)
                    v_el = cell.find(v_tag)
                    if v_el is None:
                        v_el = ET.SubElement(cell, v_tag)
                    v_el.text = str(cached_values[coord])
                raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            zout.writestr(info.filename, raw, compress_type=zipfile.ZIP_DEFLATED)
    return out_buf.getvalue()

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output" / "bank_statement" / "excel"


HEADERS = [
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
]

RUPIAH_FORMAT = '"Rp" #,##0;-"Rp" #,##0;;@'


def excel_amount(value):
    """Mengubah nominal 0 menjadi sel kosong."""
    if value is None:
        return None

    amount = Decimal(str(value))

    if amount == 0:
        return None

    return int(amount) if amount == amount.to_integral_value() else float(amount)

def export_cash_report(
    rows: list[CashReportRow],
    bank: str,
    output_path: Path | None = None,
) -> Path:

    bank = bank.strip()
    if not bank:
        raise ValueError("Nama bank tidak boleh kosong.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"Cash Report {bank}"

    # Header
    sheet.append(HEADERS)

    # Data Cash Report
    for row in rows:
        sheet.append([
            row.tanggal_input_dan_nama_admin,
            row.tanggal_transaksi,
            row.keterangan,
            row.kategori,
            row.keterangan_uang_masuk,
            row.keterangan_uang_keluar,
            excel_amount(row.debet),
            excel_amount(row.kredit),
            excel_amount(row.saldo),
            row.lampiran_nota,
        ])


    # Format tanggal dan Rupiah
    for row_index in range(2, sheet.max_row + 1):
        sheet.cell(row_index, 2).number_format = "DD-MMM-YY"

        for col in (7, 8, 9):
            sheet.cell(row_index, col).number_format = RUPIAH_FORMAT

    # Ringkasan Cash Report: Subtotal, Sisa Saldo, Grand Total
    last_data_row = sheet.max_row

    subtotal_row = last_data_row + 1
    sisa_saldo_row = subtotal_row + 1
    grand_total_row = sisa_saldo_row + 1

    # Gabungkan kolom B dan C, lalu beri label bold
    summary_labels = {
        subtotal_row: "SUB TOTAL",
        sisa_saldo_row: "SISA SALDO",
        grand_total_row: "GRAND TOTAL"
    }

    for row_index, label in summary_labels.items():
        sheet.merge_cells(
            start_row=row_index,
            start_column=2,
            end_row=row_index,
            end_column=3
        )

        cell = sheet.cell(row=row_index, column=2)
        cell.value = label
        cell.font = Font(bold=True)


    # SUB TOTAL
    sheet.cell(
        subtotal_row, 7,
        f"=SUM(G2:G{last_data_row})"
    )

    sheet.cell(
        subtotal_row, 8,
        f"=SUM(H2:H{last_data_row})"
    )


    # SISA SALDO
    sheet.cell(
        sisa_saldo_row, 8,
        f"=G{subtotal_row}-H{subtotal_row}"
    )


    # GRAND TOTAL
    sheet.cell(
        grand_total_row, 7,
        f"=G{subtotal_row}"
    )

    sheet.cell(
        grand_total_row, 8,
        f"=H{subtotal_row}+H{sisa_saldo_row}"
    )


    # Format Rupiah dan bold untuk nominal ringkasan
    for row_index in summary_labels:
        for col in (7, 8):
            cell = sheet.cell(row=row_index, column=col)
            cell.number_format = RUPIAH_FORMAT
            cell.font = Font(bold=True)

    

    
    # PERSETUJUAN CASH REPORT
    approval_row = grand_total_row + 3
    name_row = approval_row + 5

    sheet.cell(approval_row, 2, "Disetujui Oleh,")
    sheet.cell(approval_row, 8, "Disusun Oleh,")

    sheet.cell(
        name_row, 2,
        "(Ilham Nawan Rasyid, S.T.P.)"
    )

    sheet.cell(
        name_row, 8,
        "(Chikaristin Pratiwi)"
    )

    for row_index in (approval_row, name_row):
        for col_index in (2, 8):
            cell = sheet.cell(row_index, col_index)
            cell.font = Font(name="Arial", size=10)
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center"
            )



    # Simpan file Excel (export file) dengan cached formula values
    total_debet = sum((Decimal(str(r.debet or 0)) for r in rows), Decimal("0"))
    total_kredit = sum((Decimal(str(r.kredit or 0)) for r in rows), Decimal("0"))
    sisa_saldo = total_debet - total_kredit
    grand_kredit = total_kredit + sisa_saldo
    cached_footer = {
        f"G{subtotal_row}": _num_for_excel(total_debet) or 0,
        f"H{subtotal_row}": _num_for_excel(total_kredit) or 0,
        f"H{sisa_saldo_row}": _num_for_excel(sisa_saldo) or 0,
        f"G{grand_total_row}": _num_for_excel(total_debet) or 0,
        f"H{grand_total_row}": _num_for_excel(grand_kredit) or 0,
    }

    if output_path is None:
        safe_bank = bank.replace("/", "_").replace(" ", "_")
        output_path = OUTPUT_DIR / f"Cash_Report_{safe_bank}.xlsx"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    buf = BytesIO()
    workbook.save(buf)
    output_path.write_bytes(_inject_cached_formula_values(buf.getvalue(), cached_footer))

    print(f"Excel berhasil dibuat: {output_path}")

    return output_path


_CASH_REPORT_WIDTHS = [28.0, 18.0, 56.0, 36.0, 22.0, 22.0, 20.0, 20.0, 20.0, 28.0]
_RP_FORMAT_INT = '_-"Rp"* #,##0_-;\\-"Rp"* #,##0_-;_-"Rp"* "-"_-;_-@'
_RP_FORMAT_DEC = '_-"Rp"* #,##0.00_-;\\-"Rp"* #,##0.00_-;_-"Rp"* "-"_-;_-@'
_THIN_SIDE = Side(style="thin", color="000000")
_BORDER_ALL = Border(top=_THIN_SIDE, left=_THIN_SIDE, bottom=_THIN_SIDE, right=_THIN_SIDE)
_BASE_FONT = Font(name="Calibri", size=11)
_BOLD_FONT = Font(name="Calibri", size=11, bold=True)
_TITLE_FONT = Font(name="Calibri", size=14, bold=True)


def _num_for_excel(value: Decimal | float | int | None) -> int | float | None:
    """Convert numeric value to clean int/float for Excel cells."""
    if value is None:
        return None
    amount = Decimal(str(round(float(value), 2)))
    return int(amount) if amount == amount.to_integral_value() else float(amount)


def _has_fractional_cents(values: list[float | int | None]) -> bool:
    return any(
        val is not None and abs(float(val) - round(float(val))) > 1e-6
        for val in values
    )


def _estimate_row_height(values: list[str | None], widths: list[float]) -> float:
    max_lines = 1
    for text, width in zip(values, widths):
        if not text:
            continue
        usable = max(8, int(width - 2))
        lines = sum(max(1, math.ceil(len(part) / usable)) for part in str(text).splitlines())
        if lines > max_lines:
            max_lines = lines
    return max(18.0, max_lines * 15.0 + 4.0)


def sanitize_sheet_title(raw: str) -> str:
    """Sanitize worksheet title to satisfy Excel constraints (<=31 chars, no forbidden chars)."""
    cleaned = re.sub(r"[\\/?*\[\]:]", " ", raw).strip().strip("'")
    return (cleaned[:31].rstrip().strip("'") or "Cash Report")


def build_rekonsiliasi_cash_report_bytes(report: dict) -> bytes:
    """Render full Cash Report workbook from rekonsiliasi report payload using openpyxl."""
    workbook = Workbook()
    ws = workbook.active
    ws.title = sanitize_sheet_title(report["sheet_name"])
    ws.views.sheetView[0].showGridLines = True
    ws.freeze_panes = "A6"
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    for idx, width in enumerate(_CASH_REPORT_WIDTHS, start=1):
        col_letter = ws.cell(row=1, column=idx).column_letter
        ws.column_dimensions[col_letter].width = width

    title_lines = [
        report["company"],
        f"{report['title']} ({report['subtitle']})" if report.get("subtitle") else report["title"],
        report["periode"],
    ]
    for r, text in enumerate(title_lines, start=1):
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=9)
        cell = ws.cell(row=r, column=2, value=text)
        cell.font = _TITLE_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[r].height = 24.0 if len(text) <= 80 else 36.0

    header_row = 5
    ws.row_dimensions[header_row].height = 32.0
    for col_idx, label in enumerate(HEADERS, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=label)
        cell.font = _BOLD_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER_ALL

    rows = report["rows"]
    numeric_samples = [
        report["saldo_awal"],
        report["sub_total_debet"],
        report["total_kredit"],
        report["sisa_saldo"],
        report["saldo_akhir"],
        *[item["debet"] for item in rows],
        *[item["kredit"] for item in rows],
        *[item["saldo"] for item in rows],
    ]
    rp_fmt = _RP_FORMAT_DEC if _has_fractional_cents(numeric_samples) else _RP_FORMAT_INT

    def _style_data_row(row_idx: int) -> None:
        for c in range(1, 11):
            cell = ws.cell(row=row_idx, column=c)
            cell.font = _BASE_FONT
            cell.border = _BORDER_ALL
            if c in (1, 3, 4, 5, 6, 10):
                cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
            elif c == 2:
                cell.alignment = Alignment(horizontal="left", vertical="top")
                cell.number_format = "DD-MMM-YY"
            else:
                cell.alignment = Alignment(horizontal="right", vertical="top")
                cell.number_format = rp_fmt

    first_data_row = 6
    month_start = date.fromisoformat(f"{report['month']}-01")
    saldo_awal_val = _num_for_excel(report["saldo_awal"])
    if saldo_awal_val is None:
        saldo_awal_val = 0
    cached_values: dict[str, int | float] = {
        f"I{first_data_row}": saldo_awal_val,
    }
    saldo_cells = [
        None,
        month_start,
        "Saldo Awal",
        "Saldo Awal",
        None,
        None,
        saldo_awal_val,
        None,
        f"=G{first_data_row}",
        "-",
    ]
    for c, val in enumerate(saldo_cells, start=1):
        ws.cell(row=first_data_row, column=c, value=val)
    _style_data_row(first_data_row)
    ws.row_dimensions[first_data_row].height = 20.0

    current_row = first_data_row
    for item in rows:
        current_row += 1
        debet_val = _num_for_excel(item["debet"])
        kredit_val = _num_for_excel(item["kredit"])
        saldo_val = _num_for_excel(item["saldo"])
        cached_values[f"I{current_row}"] = saldo_val if saldo_val is not None else 0
        values = [
            item["tanggal_input_admin"],
            date.fromisoformat(item["tanggal_transaksi"]),
            item["keterangan"],
            item["kategori"],
            item["uang_masuk"] or None,
            item["uang_keluar"] or None,
            debet_val if debet_val else None,
            kredit_val if kredit_val else None,
            f"=I{current_row - 1}+G{current_row}-H{current_row}",
            item["lampiran"],
        ]
        for c, val in enumerate(values, start=1):
            ws.cell(row=current_row, column=c, value=val)
        _style_data_row(current_row)
        ws.row_dimensions[current_row].height = _estimate_row_height(
            [
                item["tanggal_input_admin"],
                None,
                item["keterangan"],
                item["kategori"],
                item["uang_masuk"],
                item["uang_keluar"],
                None,
                None,
                None,
                item["lampiran"],
            ],
            _CASH_REPORT_WIDTHS,
        )

    last_data_row = current_row
    ws.auto_filter.ref = f"A{header_row}:J{last_data_row}"

    sub_row = last_data_row + 1
    sisa_row = sub_row + 1
    grand_row = sisa_row + 1
    sub_debet_val = _num_for_excel(report["sub_total_debet"])
    total_kredit_val = _num_for_excel(report["total_kredit"])
    sisa_saldo_val = _num_for_excel(report["sisa_saldo"])
    grand_kredit_val = _num_for_excel(
        round(float(report["total_kredit"] or 0) + float(report["sisa_saldo"] or 0), 2)
    )
    footer_specs = [
        (
            sub_row,
            "SUB TOTAL",
            f"=SUM(G{first_data_row}:G{last_data_row})",
            sub_debet_val if sub_debet_val is not None else 0,
            f"=SUM(H{first_data_row}:H{last_data_row})",
            total_kredit_val if total_kredit_val is not None else 0,
        ),
        (
            sisa_row,
            "SISA SALDO",
            None,
            None,
            f"=G{sub_row}-H{sub_row}",
            sisa_saldo_val if sisa_saldo_val is not None else 0,
        ),
        (
            grand_row,
            "GRAND TOTAL",
            f"=G{sub_row}",
            sub_debet_val if sub_debet_val is not None else 0,
            f"=H{sub_row}+H{sisa_row}",
            grand_kredit_val if grand_kredit_val is not None else 0,
        ),
    ]
    for row_idx, label, g_formula, g_cached, h_formula, h_cached in footer_specs:
        for c in range(1, 11):
            cell = ws.cell(row=row_idx, column=c)
            cell.font = _BOLD_FONT
            cell.border = _BORDER_ALL
            if c in (7, 8, 9):
                cell.number_format = rp_fmt
                cell.alignment = Alignment(horizontal="right", vertical="center")
        ws.merge_cells(start_row=row_idx, start_column=2, end_row=row_idx, end_column=3)
        label_cell = ws.cell(row=row_idx, column=2, value=label)
        label_cell.alignment = Alignment(horizontal="left", vertical="center")
        if g_formula is not None:
            ws.cell(row=row_idx, column=7, value=g_formula)
            cached_values[f"G{row_idx}"] = g_cached
        if h_formula is not None:
            ws.cell(row=row_idx, column=8, value=h_formula)
            cached_values[f"H{row_idx}"] = h_cached
        ws.row_dimensions[row_idx].height = 20.0

    sign_row = grand_row + 3
    name_row = sign_row + 4
    ws.cell(row=sign_row, column=2, value="Disetujui Oleh,").font = _BASE_FONT
    ws.cell(row=sign_row, column=8, value="Disusun Oleh,").font = _BASE_FONT
    ws.cell(row=name_row, column=2, value="(..............................)").font = _BASE_FONT
    ws.cell(row=name_row, column=8, value="(..............................)").font = _BASE_FONT

    buf = BytesIO()
    workbook.save(buf)
    return _inject_cached_formula_values(buf.getvalue(), cached_values)
