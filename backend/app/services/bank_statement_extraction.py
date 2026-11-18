
"""
    1. Membaca PDF rekening koran dari folder input.
    2. Memanggil Gemini multimodal untuk ekstraksi transaksi.
    3. Menerima hasil ekstraksi tervalidasi Pydantic.
    4. Menyimpan hasil ekstraksi sebagai JSON.
    5. Mengembalikan hasil untuk validasi dan proses berikutnya.
"""

from pathlib import Path

from app.services.gemini_client import extract_from_pdf
from app.schemas.bank_statement import BankStatement


BASE_DIR = Path(__file__).resolve().parents[2]

# Folder output khusus bank statement
OUTPUT_DIR = BASE_DIR / "output" / "bank_statement" / "json"

# fungsi untuk menyimpan hasil ekstraksi ke JSON
def save_json(
    statement: BankStatement,
    output_path: Path
) -> None:
    """Menyimpan hasil ekstraksi ke JSON."""

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        statement.model_dump_json(indent=2),
        encoding="utf-8"
    )


# fungsi untuk memproses PDF rekening koran
def process_pdf(
    pdf_path: str | Path
) -> BankStatement:
    """Mengekstrak satu PDF rekening koran."""

    pdf_path = Path(pdf_path)

    # Ekstraksi menggunakan Gemini multimodal
    statement = extract_from_pdf(pdf_path)

    # Nama JSON mengikuti nama file PDF
    output_path = OUTPUT_DIR / f"{pdf_path.stem}.json"

    # Simpan hasil ekstraksi
    save_json(statement, output_path)

    print(f"JSON tersimpan: {output_path}")

    return statement


# fungsi untuk memproses seluruh PDF dalam folder input
def process_all_pdfs(
    input_dir: str | Path
) -> dict[str, BankStatement]:
    """Memproses seluruh PDF dalam folder input."""

    input_dir = Path(input_dir)

    if not input_dir.is_dir():
        raise FileNotFoundError(
            f"Folder tidak ditemukan: {input_dir}"
        )

    # Hanya membaca PDF pada folder yang ditentukan
    pdf_files = sorted(input_dir.glob("*.pdf"))

    if not pdf_files:
        raise FileNotFoundError(
            f"Tidak ada PDF di folder: {input_dir}"
        )

    results = {}

    for pdf_path in pdf_files:
        print(f"\n{pdf_path.name}")

        try:
            # Ekstraksi dan simpan JSON
            statement = process_pdf(pdf_path)

            results[pdf_path.name] = statement

        except Exception as error:
            print(
                f"Gagal memproses {pdf_path.name}: {error}"
            )

    return results
