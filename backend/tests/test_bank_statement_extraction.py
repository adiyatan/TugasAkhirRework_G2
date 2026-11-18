
from pathlib import Path

from app.services.bank_statement_extraction import process_all_pdfs
from app.services.bank_statement_validation import validate_balance


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent

INPUT_DIR = (PROJECT_DIR/ "Bukti_Terstruktur_Januari_2026"/ "06_Mutasi_Rekening")


def main():
    results = process_all_pdfs(INPUT_DIR)

    print("\nRingkasan Ekstraksi:")

    for filename, statement in results.items():
        print(f"\nFile             : {filename}")
        print(f"Bank             : {statement.bank}")
        print(f"Jumlah Transaksi : {len(statement.transaksi)}")
        print(f"Saldo Awal       : {statement.saldo_awal}")
        print(f"Saldo Akhir      : {statement.saldo_akhir}")

        # Validasi masing-masing rekening koran
        is_valid = validate_balance(statement)

        print(
            f"Status Validasi  : "
            f"{'VALID' if is_valid else 'TIDAK VALID'}"
        )

if __name__ == "__main__":
    main()
