
"""
    1. Menerima BankStatement hasil ekstraksi JSON.
    2. Menghitung total Debet dan Kredit.
    3. Memeriksa saldo setiap transaksi secara berurutan.
    4. Membandingkan saldo hitung dengan saldo akhir rekening.
    5. Mengembalikan hasil validasi.
"""

from decimal import Decimal

from app.schemas.bank_statement import BankStatement


def validate_balance_detail(statement: BankStatement) -> dict:
    """Memvalidasi konsistensi saldo rekening koran dan mengembalikan rincian hasil."""
    if statement.saldo_awal is None:
        return {
            "is_valid": False,
            "reason": "Saldo awal tidak tersedia.",
            "total_debet": Decimal("0"),
            "total_kredit": Decimal("0"),
            "saldo_hitung": None,
            "saldo_akhir": statement.saldo_akhir,
            "errors": [],
        }

    if statement.saldo_akhir is None:
        return {
            "is_valid": False,
            "reason": "Saldo akhir tidak tersedia.",
            "total_debet": Decimal("0"),
            "total_kredit": Decimal("0"),
            "saldo_hitung": None,
            "saldo_akhir": None,
            "errors": [],
        }

    if not statement.transaksi:
        return {
            "is_valid": False,
            "reason": "Tidak ada transaksi untuk divalidasi.",
            "total_debet": Decimal("0"),
            "total_kredit": Decimal("0"),
            "saldo_hitung": None,
            "saldo_akhir": statement.saldo_akhir,
            "errors": [],
        }

    total_debet = Decimal("0")
    total_kredit = Decimal("0")
    saldo_berjalan = statement.saldo_awal
    errors = []

    for index, trx in enumerate(statement.transaksi, start=1):
        total_debet += trx.debet
        total_kredit += trx.kredit

        saldo_berjalan = saldo_berjalan - trx.debet + trx.kredit

        if saldo_berjalan != trx.saldo:
            errors.append({
                "transaksi": index,
                "tanggal": str(trx.tanggal_transaksi),
                "keterangan": trx.keterangan,
                "saldo_hitung": saldo_berjalan,
                "saldo_pdf": trx.saldo,
            })

    saldo_akhir_valid = saldo_berjalan == statement.saldo_akhir
    is_valid = saldo_akhir_valid and not errors
    return {
        "is_valid": is_valid,
        "reason": "" if is_valid else "Terdapat ketidaksesuaian saldo.",
        "total_debet": total_debet,
        "total_kredit": total_kredit,
        "saldo_hitung": saldo_berjalan,
        "saldo_akhir": statement.saldo_akhir,
        "errors": errors,
    }


def validate_balance(statement: BankStatement) -> bool:
    """Memvalidasi konsistensi saldo rekening koran."""
    detail = validate_balance_detail(statement)
    if detail["saldo_hitung"] is None:
        print(detail["reason"])
        return False

    errors = detail["errors"]
    print(f"\nValidasi Saldo {statement.bank}")
    print(f"Jumlah Transaksi : {len(statement.transaksi)}")
    print(f"Total Debet      : Rp{detail['total_debet']:,.0f}")
    print(f"Total Kredit     : Rp{detail['total_kredit']:,.0f}")
    print(f"Saldo Hitung     : Rp{detail['saldo_hitung']:,.0f}")
    print(f"Saldo Akhir JSON : Rp{detail['saldo_akhir']:,.0f}")

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

    if detail["is_valid"]:
        print("\nVALID: Semua saldo konsisten.")
        return True

    print("\nTIDAK VALID: Terdapat ketidaksesuaian saldo.")
    return False
