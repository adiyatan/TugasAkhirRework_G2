
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.schemas.bank_statement import BankStatement, BankTransaction
import app.services.bank_statement_extraction as extraction_module
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


def test_process_all_pdfs_saves_json_with_mocked_extractor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_dir = tmp_path / "pdfs"
    pdf_dir.mkdir()
    (pdf_dir / "sample.pdf").write_bytes(b"%PDF-1.4\n")
    out_dir = tmp_path / "json"

    sample_stmt = BankStatement(
        bank="BNI",
        periode_awal=date(2026, 1, 1),
        periode_akhir=date(2026, 1, 1),
        saldo_awal=Decimal("1000000"),
        saldo_akhir=Decimal("800000"),
        transaksi=[
            BankTransaction(
                tanggal_transaksi=date(2026, 1, 1),
                keterangan="Transfer Keluar",
                debet=Decimal("200000"),
                kredit=Decimal("0"),
                saldo=Decimal("800000"),
            )
        ],
    )
    monkeypatch.setattr(extraction_module, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(extraction_module, "extract_from_pdf", lambda _p: sample_stmt)

    results = process_all_pdfs(pdf_dir)

    assert "sample.pdf" in results
    assert (out_dir / "sample.json").is_file()
    assert validate_balance(results["sample.pdf"]) is True
