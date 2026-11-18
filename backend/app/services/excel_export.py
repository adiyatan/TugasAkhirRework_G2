from pathlib import Path

from app.schemas.bank_statement import CashReportRow

BASE_DIR = Path(__file__).resolve().parents[2]
OUTPUT_DIR = BASE_DIR / "output" / "bank_statement" / "excel"


from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from decimal import Decimal


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
    bank: str
) -> Path:

    bank = bank.upper()

    if bank not in {"BNI", "BRI"}:
        raise ValueError("Bank harus BNI atau BRI.")

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



    # Simpan file Excel (export file)
    output_path = OUTPUT_DIR / f"Cash_Report_{bank}.xlsx"

    workbook.save(output_path)

    print(f"Excel berhasil dibuat: {output_path}")

    return output_path
