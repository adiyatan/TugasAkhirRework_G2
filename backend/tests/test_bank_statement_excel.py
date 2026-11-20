
from pathlib import Path

from openpyxl import load_workbook

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


def test_map_to_cash_report_and_export_excel(tmp_path: Path) -> None:
    json_files = sorted(JSON_DIR.glob("*.json"))
    assert json_files
    for json_path in json_files:
        statement = BankStatement.model_validate_json(json_path.read_text(encoding="utf-8"))
        assert validate_balance(statement) is True
        rows = map_to_cash_report(statement)
        assert len(rows) == len(statement.transaksi) + 1
        # Verify masuk/keluar columns match cash flow direction
        for row in rows[1:]:
            if row.debet:
                assert row.keterangan_uang_masuk == statement.bank
                assert row.keterangan_uang_keluar is None
            elif row.kredit:
                assert row.keterangan_uang_keluar == statement.bank
                assert row.keterangan_uang_masuk is None
        out = export_cash_report(rows, statement.bank, output_path=tmp_path / f"{statement.bank}.xlsx")
        assert out.is_file()
        ws_val = load_workbook(out, data_only=True).active
        sub_row = len(rows) + 2
        assert ws_val.cell(sub_row, 7).value is not None
        assert ws_val.cell(sub_row, 8).value is not None
        assert ws_val.cell(sub_row + 1, 8).value is not None
        assert ws_val.cell(sub_row + 2, 7).value == ws_val.cell(sub_row, 7).value
        assert ws_val.cell(sub_row + 2, 8).value == ws_val.cell(sub_row, 7).value