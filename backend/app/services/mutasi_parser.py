from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re

import fitz

from app.core.config import settings
from app.services.vision import VisionImage, complete_vision

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "mutasi_extraction.prompt.md"

DATE_TIME_LINE_RE = re.compile(r"^(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2}:\d{2})$")
AMOUNT_TOKEN_RE = re.compile(r"^-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?$|^-?\d+(?:[.,]\d{1,2})?$")
BRI_STOP_MARKERS = (
    "Saldo Awal",
    "Opening Balance",
    "Total Transaksi Debet",
    "Total Debit Transaction",
    "Terbilang",
    "Created By IBBIZ",
    "Halaman ",
    "Page ",
    "Apabila terdapat perbedaan",
)


class MutasiParseError(RuntimeError):
    """Raised when a PDF statement cannot be opened or parsed."""


@dataclass(frozen=True)
class ParsedMutasiRow:
    tanggal: str
    waktu: str
    uraian: str
    tipe: str  # "CR" | "DB"
    nominal: float
    saldo: float | None


@dataclass(frozen=True)
class ParsedMutasiResult:
    no_rekening: str | None
    metode_ekstraksi: str
    rows: list[ParsedMutasiRow]
    printed_saldo_awal: float | None = None
    printed_saldo_akhir: float | None = None


def parse_number(raw: object) -> float | None:
    """Parse Indonesian or English formatted numeric strings into float."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip()
    if not text:
        return None
    text = re.sub(r"(?i)rp\.?", "", text).strip().lstrip("+")
    if not text:
        return None
    negative = text.startswith("-")
    if negative:
        text = text[1:].strip()
    text = text.replace(" ", "")

    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?", text):
        normalized = text.replace(",", "")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?", text):
        normalized = text.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,2}", text):
        normalized = text.replace(",", ".")
    elif re.fullmatch(r"\d+(?:\.\d{1,2})?", text):
        normalized = text
    else:
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            return None
        normalized = digits

    try:
        value = float(normalized)
    except ValueError:
        return None
    return -value if negative else value


def normalize_date(raw: object) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{2,4})", text)
    if match:
        day, month, year = match.groups()
        full_year = f"20{year}" if len(year) == 2 else year
        return f"{full_year}-{month}-{day}"
    return None


def normalize_time(raw: object) -> str:
    if raw is None:
        return "00:00:00"
    text = re.sub(r"(?i)\s*WIB\b", "", str(raw)).strip()
    if re.fullmatch(r"\d{2}:\d{2}:\d{2}", text):
        return text
    if re.fullmatch(r"\d{2}:\d{2}", text):
        return f"{text}:00"
    return "00:00:00"


def _extract_bri_ibbiz_account(text: str) -> str | None:
    match = re.search(
        r"(?:No\.?\s*Rekening|Account\s*No)\s*(?:\n|\s)*[:]\s*(\d{8,20})",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(1)
    match = re.search(r"IBIZ_(\d{8,20})_", text)
    return match.group(1) if match else None


def _extract_bri_printed_summary(lines: list[str]) -> tuple[float | None, float | None]:
    for idx, line in enumerate(lines):
        if line in {"Saldo Awal", "Opening Balance"}:
            tail = lines[idx : idx + 12]
            nums = [parse_number(item) for item in tail if AMOUNT_TOKEN_RE.match(item)]
            nums = [n for n in nums if n is not None]
            if len(nums) >= 4:
                return nums[0], nums[3]
    return None, None


def parse_bri_ibbiz_text(pages_text: list[str]) -> ParsedMutasiResult | None:
    """Deterministic parser for BRI IBBIZ text-based PDF statements (0 AI cost)."""
    combined = "\n".join(pages_text)
    if "IBBIZ" not in combined and "IBIZ" not in combined and "Debet" not in combined:
        return None

    all_lines = [line.strip() for page in pages_text for line in page.splitlines()]
    no_rekening = _extract_bri_ibbiz_account(combined)
    printed_awal, printed_akhir = _extract_bri_printed_summary(all_lines)

    rows: list[ParsedMutasiRow] = []
    idx = 0
    total_lines = len(all_lines)

    while idx < total_lines:
        line = all_lines[idx]
        dt_match = DATE_TIME_LINE_RE.match(line)
        if not dt_match:
            idx += 1
            continue

        raw_date, raw_time = dt_match.groups()
        idx += 1
        block: list[str] = []
        while idx < total_lines:
            candidate = all_lines[idx]
            if DATE_TIME_LINE_RE.match(candidate) or any(
                candidate.startswith(marker) for marker in BRI_STOP_MARKERS
            ):
                break
            if candidate:
                block.append(candidate)
            idx += 1

        if len(block) < 4:
            continue

        numeric_tail: list[float] = []
        prefix_end = len(block)
        for pos in range(len(block) - 1, -1, -1):
            token = block[pos]
            if AMOUNT_TOKEN_RE.match(token) and ("," in token or "." in token):
                val = parse_number(token)
                if val is not None:
                    numeric_tail.append(val)
                    prefix_end = pos
                    if len(numeric_tail) == 3:
                        break
            else:
                break

        if len(numeric_tail) != 3:
            continue
        saldo, kredit, debet = numeric_tail[0], numeric_tail[1], numeric_tail[2]

        desc_lines = block[:prefix_end]
        while desc_lines and re.fullmatch(r"\d{5,9}", desc_lines[-1]):
            desc_lines.pop()
        uraian = " ".join(" ".join(desc_lines).split()).strip()
        if not uraian:
            continue

        tanggal = normalize_date(raw_date)
        waktu = normalize_time(raw_time)
        if not tanggal:
            continue

        if kredit > 0 and debet == 0:
            tipe, nominal = "CR", kredit
        elif debet > 0 and kredit == 0:
            tipe, nominal = "DB", debet
        else:
            continue

        rows.append(
            ParsedMutasiRow(
                tanggal=tanggal,
                waktu=waktu,
                uraian=uraian,
                tipe=tipe,
                nominal=nominal,
                saldo=saldo,
            )
        )

    if not rows:
        return None

    return ParsedMutasiResult(
        no_rekening=no_rekening,
        metode_ekstraksi="Deterministik (Teks PDF)",
        rows=rows,
        printed_saldo_awal=printed_awal,
        printed_saldo_akhir=printed_akhir,
    )


@lru_cache(maxsize=1)
def load_mutasi_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def render_mutasi_prompt(
    *,
    bank_hint: str,
    page_number: int,
    total_pages: int,
    accounts: list[dict],
) -> str:
    return (
        load_mutasi_prompt()
        .replace("{{BANK_HINT}}", bank_hint)
        .replace("{{PAGE_NUMBER}}", str(page_number))
        .replace("{{TOTAL_PAGES}}", str(total_pages))
        .replace("{{REKENING_PERUSAHAAN}}", json.dumps(accounts, ensure_ascii=False, indent=2))
    )


def _loads_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                raise MutasiParseError("Respons Vision AI untuk mutasi bukan JSON valid") from exc
        else:
            raise MutasiParseError("Respons Vision AI untuk mutasi bukan JSON valid")
    if not isinstance(payload, dict):
        raise MutasiParseError("Respons Vision AI harus berupa objek JSON")
    return payload


async def extract_mutasi_via_vision(
    *,
    doc: fitz.Document,
    bank_hint: str,
    accounts: list[dict],
) -> ParsedMutasiResult:
    """Render each PDF page at 2.0x scale and extract structured rows via Vision AI."""
    total_pages = len(doc)
    all_rows: list[ParsedMutasiRow] = []
    detected_rekening: str | None = None
    printed_awal: float | None = None
    printed_akhir: float | None = None

    matrix = fitz.Matrix(2.0, 2.0)
    for idx in range(total_pages):
        page = doc[idx]
        png_bytes = page.get_pixmap(matrix=matrix, alpha=False).tobytes("png")
        prompt = render_mutasi_prompt(
            bank_hint=bank_hint,
            page_number=idx + 1,
            total_pages=total_pages,
            accounts=accounts,
        )
        try:
            raw = await complete_vision(
                model=settings.vision_model,
                prompt=prompt,
                images=[
                    VisionImage(
                        slot=f"HAL-{idx + 1}",
                        filename=f"page_{idx + 1}.png",
                        content_type="image/png",
                        data=png_bytes,
                    )
                ],
                response_format={"type": "json_object"},
                max_tokens=8192,
                api_key=settings.vision_api_key or None,
            )
        except Exception as exc:
            raise MutasiParseError(f"Vision AI gagal pada halaman {idx + 1}: {exc}") from exc

        payload = _loads_json(raw)
        if not detected_rekening and payload.get("no_rekening"):
            digits = re.sub(r"\D", "", str(payload["no_rekening"]))
            if digits:
                detected_rekening = digits
        if printed_awal is None and payload.get("saldo_awal") is not None:
            printed_awal = parse_number(payload.get("saldo_awal"))
        if payload.get("saldo_akhir") is not None:
            printed_akhir = parse_number(payload.get("saldo_akhir"))

        for row in payload.get("transaksi") or []:
            if not isinstance(row, dict):
                continue
            tanggal = normalize_date(row.get("tanggal"))
            tipe = str(row.get("tipe") or "").strip().upper()
            nominal = parse_number(row.get("nominal"))
            uraian = " ".join(str(row.get("uraian") or "").split()).strip()
            if not tanggal or tipe not in {"CR", "DB"} or nominal is None or nominal <= 0 or not uraian:
                continue
            all_rows.append(
                ParsedMutasiRow(
                    tanggal=tanggal,
                    waktu=normalize_time(row.get("waktu")),
                    uraian=uraian,
                    tipe=tipe,
                    nominal=abs(nominal),
                    saldo=parse_number(row.get("saldo")),
                )
            )

    if not all_rows:
        raise MutasiParseError("Tidak ada baris transaksi mutasi yang berhasil diekstrak dari PDF")

    return ParsedMutasiResult(
        no_rekening=detected_rekening,
        metode_ekstraksi=f"Vision AI ({settings.vision_model})",
        rows=all_rows,
        printed_saldo_awal=printed_awal,
        printed_saldo_akhir=printed_akhir,
    )


async def parse_mutasi_pdf(
    pdf_bytes: bytes,
    *,
    bank_hint: str,
    accounts: list[dict],
) -> ParsedMutasiResult:
    """Two-path PDF parser: deterministic text extraction first, then Vision AI fallback."""
    if not pdf_bytes or not pdf_bytes.lstrip().startswith(b"%PDF"):
        raise MutasiParseError("File bukan dokumen PDF yang valid")
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise MutasiParseError(f"PDF tidak dapat dibuka: {exc}") from exc

    try:
        if len(doc) == 0:
            raise MutasiParseError("Dokumen PDF kosong")

        pages_text = [page.get_text() for page in doc]
        deterministic = parse_bri_ibbiz_text(pages_text)
        if deterministic is not None:
            return deterministic

        return await extract_mutasi_via_vision(doc=doc, bank_hint=bank_hint, accounts=accounts)
    finally:
        doc.close()
