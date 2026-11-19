
"""
    1. Mengonversi BankStatement menjadi CashReportRow.
    2. Menambahkan baris Saldo Awal.
    3. Melakukan mapping Debet dan Kredit.
    4. Mengisi Keterangan Uang Masuk sesuai bank.
    5. Menyiapkan data untuk ekspor Excel.
"""

from app.schemas.bank_statement import BankStatement, CashReportRow


def map_to_cash_report(
    statement: BankStatement
) -> list[CashReportRow]:
    """Mengonversi mutasi bank menjadi Cash Report."""

    rows = []

    # saldo awal hanya ditambahkan jika ada
    if statement.saldo_awal is not None:
        rows.append(
            CashReportRow(
                tanggal_transaksi=statement.periode_awal,
                keterangan="Saldo Awal",
                kategori="Saldo Awal",
                saldo=statement.saldo_awal
            )
        )

    # mapping transaksi bank ke CashReportRow
    for trx in statement.transaksi:

        # Konvensi Cash Report:
        # Debet  = uang masuk
        # Kredit = uang keluar

        cash_debet = trx.kredit if trx.kredit > 0 else None
        cash_kredit = trx.debet if trx.debet > 0 else None

        row = CashReportRow(
            tanggal_input_dan_nama_admin=None,
            tanggal_transaksi=trx.tanggal_transaksi,
            keterangan=trx.keterangan,
            kategori=None,
            keterangan_uang_masuk=statement.bank if cash_debet else None,
            keterangan_uang_keluar=statement.bank if cash_kredit else None,
            debet=cash_debet,
            kredit=cash_kredit,
            saldo=trx.saldo,
            lampiran_nota=None,
        )

        rows.append(row)

    return rows
