
"""
    Menguji konsistensi saldo BNI/BRI menggunakan
    JSON hasil ekstraksi yang sudah tersimpan.
    Tidak memanggil Gemini API.
"""

from pathlib import Path

from app.schemas.bank_statement import BankStatement
from app.services.bank_statement_validation import validate_balance


BASE_DIR = Path(__file__).resolve().parents[1]

JSON_DIR = (
    BASE_DIR / "output" / "bank_statement" / "json"
)


def main():
    if not JSON_DIR.is_dir():
        raise FileNotFoundError(
            f"Folder JSON tidak ditemukan: {JSON_DIR}"
        )

    json_files = sorted(JSON_DIR.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"Tidak ada file JSON di folder: {JSON_DIR}"
        )

    print("Validasi Saldo BNI/BRI dari JSON yang sudah tersimpan.")

    results = {}

    for json_path in json_files:
        print(f"\nMemeriksa: {json_path.name}")

        try:
            # Membaca dan memvalidasi JSON
            statement = BankStatement.model_validate_json(
                json_path.read_text(encoding="utf-8")
            )

            # Memeriksa saldo
            is_valid = validate_balance(statement)
            results[json_path.name] = is_valid

        except Exception as error:
            print(f"Gagal: {error}")
            results[json_path.name] = False

    print("\nRingkasan Validasi Saldo BNI/BRI:")

    for filename, is_valid in results.items():
        status = "VALID" if is_valid else "TIDAK VALID"
        print(f"{filename}: {status}")


if __name__ == "__main__":
    main()
