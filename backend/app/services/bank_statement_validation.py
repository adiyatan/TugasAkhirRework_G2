
"""
    1. Menerima BankStatement hasil ekstraksi JSON.
    2. Menghitung total Debet dan Kredit.
    3. Memeriksa saldo setiap transaksi secara berurutan.
    4. Membandingkan saldo hitung dengan saldo akhir rekening.
    5. Mengembalikan hasil validasi.
"""

from decimal import Decimal

from app.schemas.bank_statement import BankStatement


def validate_balance(statement: BankStatement) -> bool:
    """Memvalidasi konsistensi saldo rekening koran."""

    if statement.saldo_awal is None:
        print("Saldo awal tidak tersedia.")
        return False

    if statement.saldo_akhir is None:
        print("Saldo akhir tidak tersedia.")
        return False

    if not statement.transaksi:
        print("Tidak ada transaksi untuk divalidasi.")
        return False

    total_debet = Decimal("0")
    total_kredit = Decimal("0")
    saldo_berjalan = statement.saldo_awal
    errors = []

    for index, trx in enumerate(statement.transaksi, start=1):
        total_debet += trx.debet
        total_kredit += trx.kredit

        saldo_berjalan = (
            saldo_berjalan - trx.debet + trx.kredit
        )

        if saldo_berjalan != trx.saldo:
            errors.append({
                "transaksi": index,
                "tanggal": str(trx.tanggal_transaksi),
                "keterangan": trx.keterangan,
                "saldo_hitung": saldo_berjalan,
                "saldo_pdf": trx.saldo,
            })

    saldo_akhir_valid = saldo_berjalan == statement.saldo_akhir

    print(f"\nValidasi Saldo {statement.bank}")
    print(f"Jumlah Transaksi : {len(statement.transaksi)}")
    print(f"Total Debet      : Rp{total_debet:,.0f}")
    print(f"Total Kredit     : Rp{total_kredit:,.0f}")
    print(f"Saldo Hitung     : Rp{saldo_berjalan:,.0f}")
    print(f"Saldo Akhir JSON : Rp{statement.saldo_akhir:,.0f}")

    if errors:
        print(f"\nDitemukan {len(errors)} ketidaksesuaian saldo:")

        for error in errors:
            print(
                f"Transaksi {error['transaksi']} | "
                f"{error['tanggal']} | "
                f"{error['keterangan']} | "
                f"Hitung: Rp{error['saldo_hitung']:,.0f} | "
                f"JSON: Rp{error['saldo_pdf']:,.0f}"
            )

    if saldo_akhir_valid and not errors:
        print("\nVALID: Semua saldo konsisten.")
        return True

    print("\nTIDAK VALID: Terdapat ketidaksesuaian saldo.")
    return False
