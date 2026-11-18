
from pathlib import Path

from app.schemas.bank_statement import BankStatement
from app.services.bank_statement_validation import validate_balance
from app.services.cash_report_mapper import map_to_cash_report
from app.services.excel_export import export_cash_report


BACKEND_DIR = Path(__file__).resolve().parents[1]
JSON_DIR = BACKEND_DIR / "output" / "bank_statement" / "json"


def main():
    json_files = sorted(JSON_DIR.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"Tidak ada JSON di: {JSON_DIR}"
        )

    for json_path in json_files:
        print(f"\n=== {json_path.name} ===")

        statement = BankStatement.model_validate_json(
            json_path.read_text(encoding="utf-8")
        )

        if not validate_balance(statement):
            print("Ekspor dilewati: saldo tidak valid.")
            continue

        rows = map_to_cash_report(statement)

        output_path = export_cash_report(
            rows,
            statement.bank
        )

        print(f"Jumlah baris Cash Report: {len(rows)}")
        print(f"Excel tersimpan: {output_path}")


if __name__ == "__main__":
    main()