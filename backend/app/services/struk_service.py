from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import shutil
import uuid

from app.core.config import settings
from app.core.database import get_connection
from app.schemas.auth import UserPublic
from app.schemas.struk import (
    StrukMetadata,
    StrukSaveRequest,
    StrukTransactionFields,
    StrukUpdateRequest,
)
from app.services.ai_service import (
    build_usage_payload,
    get_active_vision_model,
    record_ai_usage,
)
from app.services.rekonsiliasi_service import (
    auto_reconcile_transaction,
    unlink_reconciliation_for_transaction,
)
from app.services.storage import (
    UploadValidationError,
    safe_stored_filename,
    storage_root,
    validate_upload,
    write_staging_file,
)
from app.services.vision import (
    VisionImage,
    complete_vision,
    consume_last_vision_usage,
    reset_last_vision_usage,
)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "receipt_extraction.prompt.md"
TAB_TYPES = {"normal", "flip", "slip_gaji", "reimburse"}
TOP_LEVEL_KEYS = {
    "tanggal_transaksi",
    "waktu_transaksi",
    "rekening",
    "rekening_tujuan",
    "tipe",
    "kategori",
    "penerima_pengirim",
    "keterangan",
    "nominal_pokok",
    "biaya_admin_kode_unik",
    "total_mutasi",
    "jenis_struk",
    "slot_a",
    "slot_b",
    "slot_c",
    "notes",
}
FILE_KEYS = {
    "filename",
    "document_type",
    "amount",
    "date",
    "time",
    "sender_digits",
    "recipient_digits",
    "company_account",
    "sender_excluded",
    "is_unpaid",
}
SALARY_CATEGORIES = {"Biaya-Gaji Karyawan", "Pendapatan/Beban Lain"}
PINDAH_BUKU_CATEGORY = "Transfer Antar Rekening (Pindah Buku)"
FLIP_DOC_TYPES = {"flip_bank_to_fliptech", "flip_to_recipient"}


class StrukError(Exception):
    """Base error that the router can translate into an HTTP response."""

    status_code = 400

    def __init__(self, message: str, *, errors: list[str] | None = None, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.errors = errors or [message]
        if status_code is not None:
            self.status_code = status_code


class StrukConflictError(StrukError):
    status_code = 409


class StrukUpstreamError(StrukError):
    status_code = 502


@dataclass(frozen=True)
class ReceiptUpload:
    slot: str
    filename: str
    content_type: str
    data: bytes


def _as_int(value: object, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _digits(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def _loads_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError:
                raise StrukUpstreamError("Respons vision bukan JSON yang valid") from exc
        else:
            raise StrukUpstreamError("Respons vision bukan JSON yang valid") from exc
    if not isinstance(payload, dict):
        raise StrukUpstreamError("Respons vision harus berupa objek JSON")
    return payload


def _validate_payload(payload: dict, expected_counts: dict[str, int]) -> None:
    missing = TOP_LEVEL_KEYS - set(payload)
    if missing:
        raise StrukUpstreamError(f"Respons vision kehilangan field: {', '.join(sorted(missing))}")

    for key, expected in expected_counts.items():
        rows = payload.get(key)
        if not isinstance(rows, list):
            raise StrukUpstreamError(f"{key} harus berupa array")
        if len(rows) != expected:
            raise StrukUpstreamError(
                f"Jumlah objek {key} ({len(rows)}) tidak sama dengan jumlah file ({expected})"
            )
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise StrukUpstreamError(f"{key}[{index}] harus berupa objek")
            missing_file_keys = FILE_KEYS - set(row)
            if missing_file_keys:
                raise StrukUpstreamError(
                    f"{key}[{index}] kehilangan field: {', '.join(sorted(missing_file_keys))}"
                )


@lru_cache(maxsize=1)
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def render_prompt(tab_type: str, is_cash: bool, metadata: StrukMetadata) -> str:
    accounts = [row.model_dump() for row in metadata.rekening_perusahaan]
    categories = [row.model_dump() for row in metadata.kategori_sop]
    excluded = [row.model_dump() for row in metadata.rekening_dikecualikan]
    return (
        load_prompt()
        .replace("{{TAB_TYPE}}", tab_type)
        .replace("{{IS_CASH}}", "true" if is_cash else "false")
        .replace("{{REKENING_PERUSAHAAN}}", json.dumps(accounts, ensure_ascii=False, indent=2))
        .replace("{{REKENING_DIKECUALIKAN}}", json.dumps(excluded, ensure_ascii=False, indent=2))
        .replace("{{KATEGORI_SOP}}", json.dumps(categories, ensure_ascii=False, indent=2))
    )


class StrukService:
    """Business logic for the Input Struk workflow."""

    def get_metadata(self) -> StrukMetadata:
        with get_connection() as conn:
            rekening_rows = conn.execute(
                """
                SELECT id, kode_akun, bank_lembaga, no_rekening, atas_nama, peran, is_cash
                FROM rekening_perusahaan
                WHERE is_active = 1
                ORDER BY is_cash ASC, id ASC
                """
            ).fetchall()
            kategori_rows = conn.execute(
                """
                SELECT id, no_urut, nama_kategori, kelompok
                FROM kategori_sop
                WHERE is_active = 1
                ORDER BY no_urut ASC
                """
            ).fetchall()
            excluded_rows = conn.execute(
                """
                SELECT id, nama_pemilik, potongan_no_rek, keterangan
                FROM rekening_dikecualikan
                WHERE is_active = 1
                ORDER BY id ASC
                """
            ).fetchall()

        return StrukMetadata(
            rekening_perusahaan=[
                {
                    **dict(row),
                    "is_cash": bool(row["is_cash"]),
                }
                for row in rekening_rows
            ],
            kategori_sop=[dict(row) for row in kategori_rows],
            rekening_dikecualikan=[dict(row) for row in excluded_rows],
            tabs=["normal", "flip", "slip_gaji", "reimburse"],
        )

    async def extract(
        self,
        *,
        user: UserPublic,
        tab_type: str,
        is_cash: bool,
        slot_a: list[ReceiptUpload],
        slot_b: list[ReceiptUpload],
        slot_c: list[ReceiptUpload],
    ) -> dict:
        if tab_type not in TAB_TYPES:
            raise StrukError("Mode tab tidak valid")
        self._validate_slots(tab_type, is_cash, slot_a, slot_b, slot_c)

        uploads = [*slot_a, *slot_b, *slot_c]
        for upload in uploads:
            try:
                validate_upload(upload.filename, upload.content_type, upload.data)
            except UploadValidationError as exc:
                raise StrukError(str(exc)) from exc
        self._reject_duplicate_hashes(uploads)

        metadata = self.get_metadata()
        images = [
            VisionImage(
                slot=upload.slot,
                filename=upload.filename,
                content_type=upload.content_type,
                data=upload.data,
            )
            for upload in uploads
        ]
        prompt = render_prompt(tab_type, is_cash, metadata)
        active_model = get_active_vision_model()
        reset_last_vision_usage()
        try:
            raw = await complete_vision(
                model=active_model,
                prompt=prompt,
                images=images,
                response_format={"type": "json_object"},
                api_key=settings.vision_api_key or None,
            )
        except Exception as exc:
            consume_last_vision_usage()
            raise StrukUpstreamError(f"Vision provider gagal: {exc}") from exc
        ai_usage = build_usage_payload(
            consume_last_vision_usage(),
            model=active_model,
            used_ai=True,
            pages_processed=len(images),
        )

        payload = _loads_json(raw)
        _validate_payload(
            payload,
            {
                "slot_a": len(slot_a),
                "slot_b": len(slot_b),
                "slot_c": len(slot_c),
            },
        )

        extracted, errors, warnings, locked_fields = self._apply_rules(
            tab_type=tab_type,
            is_cash=is_cash,
            payload=payload,
            metadata=metadata,
        )
        manifest = self._build_manifest(uploads, payload)
        staging_id = f"stg_{uuid.uuid4().hex}"
        inserted_files: list[Path] = []
        try:
            for row, upload in zip(manifest, uploads, strict=True):
                stored_name = safe_stored_filename(upload.filename, row["sha256"], upload.slot)
                inserted_files.append(write_staging_file(staging_id, stored_name, upload.data))
                row["stored_name"] = stored_name

            if not errors:
                warning = self._semantic_duplicate_warning(extracted)
                if warning:
                    warnings.append(warning)

            mutasi_hint = self._mutasi_hint(extracted) if not errors else None
            expires_at = (
                datetime.now(timezone.utc) + timedelta(minutes=settings.staging_ttl_minutes)
            ).replace(microsecond=0).isoformat()
            user_id = self._user_id(user.username)
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO upload_staging (
                        id, user_id, tab_type, is_cash, status, manifest_json,
                        extracted_json, ai_usage_json, expires_at
                    ) VALUES (?, ?, ?, ?, 'OPEN', ?, ?, ?, ?)
                    """,
                    (
                        staging_id,
                        user_id,
                        tab_type,
                        1 if is_cash else 0,
                        json.dumps(manifest, ensure_ascii=False),
                        json.dumps(extracted, ensure_ascii=False),
                        json.dumps(ai_usage, ensure_ascii=False),
                        expires_at,
                    ),
                )
                conn.commit()
            record_ai_usage(
                feature="input_struk",
                usage=ai_usage,
                user_id=user_id,
                reference_type="staging",
                reference_id=staging_id,
            )
        except Exception:
            shutil.rmtree(storage_root() / "staging" / staging_id, ignore_errors=True)
            raise

        return {
            "staging_id": staging_id,
            "tab_type": tab_type,
            "is_cash": is_cash,
            "expires_at": expires_at,
            "extracted": extracted,
            "slots": {
                "A": [row for row in manifest if row["slot"] == "A"],
                "B": [row for row in manifest if row["slot"] == "B"],
                "C": [row for row in manifest if row["slot"] == "C"],
            },
            "manifest": manifest,
            "warnings": warnings,
            "errors": errors,
            "locked_fields": locked_fields,
            "mutasi_hint": mutasi_hint,
            "ai_usage": ai_usage,
        }

    def _validate_slots(
        self,
        tab_type: str,
        is_cash: bool,
        slot_a: list[ReceiptUpload],
        slot_b: list[ReceiptUpload],
        slot_c: list[ReceiptUpload],
    ) -> None:
        if not slot_a:
            raise StrukError("Slot A wajib berisi minimal satu file")
        if tab_type == "flip":
            if len(slot_a) != 1:
                raise StrukError("Tab flip wajib memiliki tepat 1 file Slot A")
            if not slot_b:
                raise StrukError("Tab flip wajib memiliki minimal 1 file Slot B")
        elif tab_type in {"slip_gaji", "reimburse"} and not slot_b:
            raise StrukError(f"Tab {tab_type} wajib memiliki minimal 1 file Slot B")
        if is_cash and tab_type != "normal":
            raise StrukError("Transaksi cash hanya tersedia untuk tab normal")
        if slot_c and tab_type != "flip":
            raise StrukError("Slot C hanya tersedia untuk tab flip")

    def _reject_duplicate_hashes(self, uploads: list[ReceiptUpload]) -> None:
        seen: dict[str, str] = {}
        for upload in uploads:
            file_hash = hashlib.sha256(upload.data).hexdigest()
            if file_hash in seen:
                raise StrukError(
                    f"File duplikat di dalam batch: {upload.filename} sama dengan {seen[file_hash]}"
                )
            seen[file_hash] = upload.filename

        for file_hash in seen:
            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT fbl.orig_filename, ti.id AS transaksi_id
                    FROM file_bukti_log fbl
                    JOIN transaksi_internal ti ON ti.id = fbl.transaksi_internal_id
                    WHERE fbl.file_hash = ?
                    LIMIT 1
                    """,
                    (file_hash,),
                ).fetchone()
            if row:
                raise StrukConflictError(
                    f"Duplikat file {row['orig_filename']} sudah tercatat pada transaksi #{row['transaksi_id']}"
                )

    def _build_manifest(self, uploads: list[ReceiptUpload], payload: dict) -> list[dict]:
        slot_rows = {
            "A": payload["slot_a"],
            "B": payload["slot_b"],
            "C": payload["slot_c"],
        }
        indexes = {"A": 0, "B": 0, "C": 0}
        manifest: list[dict] = []
        for upload in uploads:
            row = slot_rows[upload.slot][indexes[upload.slot]]
            indexes[upload.slot] += 1
            manifest.append(
                {
                    "slot": upload.slot,
                    "filename": upload.filename,
                    "orig_filename": upload.filename,
                    "content_type": upload.content_type,
                    "size": len(upload.data),
                    "sha256": hashlib.sha256(upload.data).hexdigest(),
                    "document_type": row.get("document_type"),
                    "amount": _as_int(row.get("amount")),
                    "date": row.get("date"),
                    "time": row.get("time"),
                }
            )
        return manifest

    @staticmethod
    def _slot_b_main_and_total(slot_b: list[dict]) -> tuple[dict, int, list[dict]]:
        """Pick primary Bank->Flip (or non-recipient) row and total mutasi without double-counting Flip pairs."""
        flip_b = [row for row in slot_b if row.get("document_type") == "flip_to_recipient"]
        non_recipient = [row for row in slot_b if row.get("document_type") != "flip_to_recipient"]
        main = next(
            (row for row in slot_b if row.get("document_type") == "flip_bank_to_fliptech"),
            non_recipient[0] if non_recipient else slot_b[0],
        )
        has_flip_main = any(row.get("document_type") == "flip_bank_to_fliptech" for row in slot_b)
        total = (
            _as_int(main.get("amount"))
            if has_flip_main or flip_b
            else sum(_as_int(row.get("amount")) for row in slot_b)
        )
        return main, total, flip_b

    def _apply_rules(
        self,
        *,
        tab_type: str,
        is_cash: bool,
        payload: dict,
        metadata: StrukMetadata,
    ) -> tuple[dict, list[str], list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []
        locked_fields: list[str] = []
        accounts = [row.model_dump() for row in metadata.rekening_perusahaan]
        excluded = [row.model_dump() for row in metadata.rekening_dikecualikan]
        categories = {row.nama_kategori: row for row in metadata.kategori_sop}

        extracted = {
            "tanggal_transaksi": payload.get("tanggal_transaksi"),
            "waktu_transaksi": payload.get("waktu_transaksi") or "12:00:00",
            "rekening": payload.get("rekening"),
            "rekening_tujuan": payload.get("rekening_tujuan"),
            "tipe": payload.get("tipe") or "KELUAR",
            "kategori": payload.get("kategori"),
            "penerima_pengirim": payload.get("penerima_pengirim") or "",
            "keterangan": payload.get("keterangan") or "",
            "nominal_pokok": _as_int(payload.get("nominal_pokok")),
            "biaya_admin_kode_unik": _as_int(payload.get("biaya_admin_kode_unik")),
            "total_mutasi": _as_int(payload.get("total_mutasi")),
            "jenis_struk": payload.get("jenis_struk") or "unknown",
            "notes": payload.get("notes") or "",
            "slot_a": payload["slot_a"],
            "slot_b": payload["slot_b"],
            "slot_c": payload["slot_c"],
        }

        kategori = categories.get(extracted["kategori"])
        if not kategori:
            errors.append("Kategori tidak ada di daftar kategori_sop")
        extracted["kategori_id"] = kategori.id if kategori else None

        if tab_type == "normal":
            slot_a = payload["slot_a"]
            if is_cash:
                cash_account = next((row for row in accounts if row["is_cash"]), None)
                if cash_account:
                    extracted["rekening"] = cash_account["kode_akun"]
                    extracted["rekening_sumber_id"] = cash_account["id"]
                extracted["tipe"] = "KELUAR"
                total = sum(_as_int(row.get("amount")) for row in slot_a)
                extracted["total_mutasi"] = total
                extracted["nominal_pokok"] = total
                extracted["biaya_admin_kode_unik"] = 0
                locked_fields.extend(["rekening", "rekening_sumber_id", "tipe"])
                if total > 0:
                    locked_fields.append("total_mutasi")
            else:
                if any(bool(row.get("is_unpaid")) for row in slot_a):
                    errors.append("Struk Slot A masih berstatus Belum Bayar; gunakan bukti pembayaran yang sah")
                is_incoming = extracted.get("tipe") == "MASUK"
                bad_flip = any(
                    row.get("document_type") == "flip_bank_to_fliptech"
                    or (not is_incoming and row.get("document_type") in FLIP_DOC_TYPES)
                    for row in slot_a
                )
                if bad_flip:
                    errors.append("Struk Flip terdeteksi di tab normal; gunakan tab flip")
                if not is_incoming and any(self._file_is_excluded(row, excluded) for row in slot_a):
                    errors.append(
                        "Pengirim berasal dari rekening_dikecualikan; gunakan tab reimburse"
                    )
                source = self._account_from_file(slot_a[0], accounts, preference="sender")
                destination = self._account_from_file(slot_a[0], accounts, preference="recipient")
                if source:
                    extracted["rekening"] = source["kode_akun"]
                    extracted["rekening_sumber_id"] = source["id"]
                if source and destination and source["id"] != destination["id"]:
                    extracted["tipe"] = "PINDAH_BUKU"
                    extracted["rekening_tujuan"] = destination["kode_akun"]
                    extracted["rekening_tujuan_id"] = destination["id"]
                    extracted["kategori"] = PINDAH_BUKU_CATEGORY
                    extracted["kategori_id"] = categories[PINDAH_BUKU_CATEGORY].id
                    locked_fields.extend(
                        [
                            "tipe",
                            "kategori",
                            "kategori_id",
                            "rekening_tujuan",
                            "rekening_tujuan_id",
                        ]
                    )
                total = sum(_as_int(row.get("amount")) for row in slot_a)
                extracted["total_mutasi"] = total
                extracted["nominal_pokok"] = total
                extracted["biaya_admin_kode_unik"] = 0

        elif tab_type == "flip":
            slot_a = payload["slot_a"][0]
            slot_b = payload["slot_b"]
            source = self._account_from_file(slot_a, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            total = _as_int(slot_a.get("amount"))
            nominal = sum(_as_int(row.get("amount")) for row in slot_b)
            biaya = total - nominal
            extracted["total_mutasi"] = total
            extracted["nominal_pokok"] = nominal
            extracted["biaya_admin_kode_unik"] = biaya
            extracted["tanggal_transaksi"] = slot_a.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = slot_a.get("time") or extracted["waktu_transaksi"]
            extracted["tipe"] = "KELUAR"
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "nominal_pokok",
                    "biaya_admin_kode_unik",
                    "total_mutasi",
                ]
            )
            if biaya < 0 or biaya > 1000:
                errors.append(
                    "Selisih total mutasi dan nominal pokok Flip di luar batas Rp1.000"
                )
            dates = {row.get("date") for row in slot_b if row.get("date")}
            if dates and extracted["tanggal_transaksi"] not in dates:
                warnings.append("Tanggal Slot A berbeda dengan tanggal Slot B")
            destination = next(
                (
                    account
                    for row in slot_b
                    if (account := self._account_from_file(row, accounts, preference="recipient"))
                ),
                None,
            )
            if destination and source and destination["id"] != source["id"]:
                extracted["tipe"] = "PINDAH_BUKU"
                extracted["rekening_tujuan"] = destination["kode_akun"]
                extracted["rekening_tujuan_id"] = destination["id"]
                extracted["kategori"] = PINDAH_BUKU_CATEGORY
                extracted["kategori_id"] = categories[PINDAH_BUKU_CATEGORY].id
                locked_fields.extend(
                    ["tipe", "kategori", "kategori_id", "rekening_tujuan", "rekening_tujuan_id"]
                )

        elif tab_type == "slip_gaji":
            slot_a = payload["slot_a"]
            slot_b = payload["slot_b"]
            main, total, flip_b = self._slot_b_main_and_total(slot_b)
            extracted["tanggal_transaksi"] = main.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = main.get("time") or extracted["waktu_transaksi"]
            source = self._account_from_file(main, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            nominal = sum(_as_int(row.get("amount")) for row in flip_b) if flip_b else total
            biaya = total - nominal
            extracted["tipe"] = "KELUAR"
            extracted["total_mutasi"] = total
            extracted["nominal_pokok"] = nominal
            extracted["biaya_admin_kode_unik"] = biaya
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "total_mutasi",
                    "nominal_pokok",
                ]
            )
            if extracted["kategori"] not in SALARY_CATEGORIES:
                errors.append("Kategori slip gaji harus Biaya-Gaji Karyawan atau Pendapatan/Beban Lain")
            if flip_b and (biaya < 0 or biaya > 1000):
                errors.append("Selisih transfer gaji via Flip di luar batas Rp1.000")
            slip_total = sum(_as_int(row.get("amount")) for row in slot_a)
            if slip_total and slip_total != nominal:
                warnings.append("Nominal slip gaji berbeda dengan nominal transfer")

        elif tab_type == "reimburse":
            slot_a = payload["slot_a"]
            slot_b = payload["slot_b"]
            main, total, _ = self._slot_b_main_and_total(slot_b)
            extracted["tanggal_transaksi"] = main.get("date") or extracted["tanggal_transaksi"]
            extracted["waktu_transaksi"] = main.get("time") or extracted["waktu_transaksi"]
            source = self._account_from_file(main, accounts, preference="sender")
            if source:
                extracted["rekening"] = source["kode_akun"]
                extracted["rekening_sumber_id"] = source["id"]
            nota_total = sum(_as_int(row.get("amount")) for row in slot_a)
            diff = total - nota_total
            extracted["tipe"] = "KELUAR"
            extracted["total_mutasi"] = total
            if 0 <= diff <= 1000:
                extracted["nominal_pokok"] = nota_total
                extracted["biaya_admin_kode_unik"] = diff
            elif -1000 <= diff < 0:
                extracted["nominal_pokok"] = total
                extracted["biaya_admin_kode_unik"] = 0
                warnings.append(
                    f"Nominal penggantian lebih kecil Rp{abs(diff):,} dari nota awal (dalam batas toleransi Rp1.000)".replace(",", ".")
                )
            else:
                extracted["nominal_pokok"] = nota_total
                extracted["biaya_admin_kode_unik"] = max(0, diff)
            locked_fields.extend(
                [
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening",
                    "rekening_sumber_id",
                    "tipe",
                    "total_mutasi",
                    "nominal_pokok",
                ]
            )
            if any(self._file_is_excluded(row, excluded) for row in slot_b):
                errors.append("Pengirim Slot B berasal dari rekening_dikecualikan; reimburse diblokir")
            if abs(diff) > 1000:
                errors.append("Selisih nota awal dan transfer penggantian melebihi Rp1.000")

        if extracted.get("rekening_sumber_id") is None:
            source = next(
                (row for row in accounts if row["kode_akun"] == extracted.get("rekening")),
                None,
            )
            if source:
                extracted["rekening_sumber_id"] = source["id"]
            else:
                errors.append("Rekening sumber tidak dikenal")
        if extracted.get("rekening_tujuan"):
            destination = next(
                (row for row in accounts if row["kode_akun"] == extracted.get("rekening_tujuan")),
                None,
            )
            if destination:
                extracted["rekening_tujuan_id"] = destination["id"]
            else:
                errors.append("Rekening tujuan tidak dikenal")
        else:
            extracted["rekening_tujuan_id"] = None

        return extracted, errors, warnings, sorted(set(locked_fields))

    def _matches_account_digits(self, candidate: str, account_raw: str) -> bool:
        if len(candidate) < 3:
            return False
        numbers = [d for part in re.split(r"[,;/]+", account_raw) if (d := _digits(part))]
        for number in numbers:
            if len(candidate) >= 6:
                if candidate in number or number in candidate:
                    return True
            elif number.endswith(candidate):
                return True
        return False

    def _file_is_excluded(self, row: dict, excluded: list[dict]) -> bool:
        if bool(row.get("sender_excluded")):
            return True
        sender = _digits(row.get("sender_digits"))
        if not sender:
            return False
        return any(
            item["potongan_no_rek"] and self._matches_account_digits(sender, item["potongan_no_rek"])
            for item in excluded
        )

    def _account_from_file(
        self,
        row: dict,
        accounts: list[dict],
        *,
        preference: str,
    ) -> dict | None:
        digits = _digits(row.get("recipient_digits" if preference == "recipient" else "sender_digits"))
        if digits:
            for account in accounts:
                if self._matches_account_digits(digits, account["no_rekening"]):
                    return account
        company_account = row.get("company_account")
        if preference == "sender" and company_account:
            match = next((item for item in accounts if item["kode_akun"] == company_account), None)
            if match:
                return match
        return None

    def _semantic_duplicate_warning(self, extracted: dict) -> str | None:
        if not extracted.get("tanggal_transaksi") or not extracted.get("rekening_sumber_id"):
            return None
        total = extracted.get("total_mutasi") or 0
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM transaksi_internal
                WHERE tanggal_transaksi = ?
                  AND rekening_sumber_id = ?
                  AND ABS(total_mutasi - ?) <= 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    extracted["tanggal_transaksi"],
                    extracted["rekening_sumber_id"],
                    total,
                ),
            ).fetchone()
        if row:
            return f"Indikasi duplikat transaksi dengan transaksi #{row['id']}"
        return None

    def _mutasi_hint(self, extracted: dict) -> dict | None:
        if not extracted.get("tanggal_transaksi") or not extracted.get("rekening_sumber_id"):
            return None
        try:
            center = date.fromisoformat(extracted["tanggal_transaksi"])
        except ValueError:
            return None
        start = (center - timedelta(days=1)).isoformat()
        end = (center + timedelta(days=1)).isoformat()
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS total FROM mutasi_bank
                WHERE rekening_id = ? AND tanggal BETWEEN ? AND ?
                """,
                (extracted["rekening_sumber_id"], start, end),
            ).fetchone()
        if row and row["total"]:
            return {
                "found": True,
                "message": "Ditemukan indikasi kecocokan di mutasi",
            }
        return {"found": False, "message": "Belum ada di mutasi"}

    def save(self, *, user: UserPublic, payload: StrukSaveRequest) -> dict:
        user_id = self._user_id(user.username)
        with get_connection() as conn:
            staging = conn.execute(
                "SELECT * FROM upload_staging WHERE id = ?",
                (payload.staging_id,),
            ).fetchone()
        if not staging:
            raise StrukError("Staging tidak ditemukan", status_code=404)
        if staging["user_id"] != user_id and user.role not in {"finance", "management"}:
            raise StrukError("Staging ini bukan milik user", status_code=403)
        if staging["status"] != "OPEN":
            raise StrukConflictError("Staging sudah diproses atau tidak aktif")
        if self._is_expired(staging["expires_at"]):
            with get_connection() as conn:
                conn.execute(
                    "UPDATE upload_staging SET status = 'EXPIRED' WHERE id = ? AND status = 'OPEN'",
                    (payload.staging_id,),
                )
                conn.commit()
            raise StrukConflictError("Staging sudah kedaluwarsa")

        manifest = json.loads(staging["manifest_json"] or "[]")
        extracted = json.loads(staging["extracted_json"] or "{}")
        ai_usage = json.loads(staging["ai_usage_json"] or "{}") if "ai_usage_json" in staging.keys() else {}
        tab_type = staging["tab_type"]
        is_cash = bool(staging["is_cash"])
        self._validate_locked_fields(tab_type, extracted, payload, is_cash=is_cash)
        self._recheck_hashes(manifest)
        self._validate_save_payload(payload, tab_type, is_cash=is_cash, extracted=extracted)
        if not payload.force_save_duplicate:
            duplicate = self._find_semantic_duplicate(payload)
            if duplicate:
                raise StrukConflictError(
                    f"Indikasi duplikat dengan transaksi #{duplicate}; gunakan force_save_duplicate untuk tetap menyimpan"
                )

        moved: list[tuple[Path, Path]] = []
        try:
            moved = self._move_manifest_files(payload.staging_id, manifest)
            with get_connection() as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    claimed = conn.execute(
                        """
                        UPDATE upload_staging
                        SET status = 'SAVED'
                        WHERE id = ? AND status = 'OPEN'
                        """,
                        (payload.staging_id,),
                    )
                    if claimed.rowcount != 1:
                        raise StrukConflictError("Staging sudah diproses oleh request lain")
                    transaksi_id = conn.execute(
                        """
                        INSERT INTO transaksi_internal (
                            staging_id, created_by_user_id, nama_admin, tanggal_input,
                            sumber_pencatatan, tab_type, tanggal_transaksi, waktu_transaksi,
                            rekening_sumber_id, rekening_tujuan_id, tipe, kategori_id,
                            penerima_pengirim, keterangan, nominal_pokok,
                            biaya_admin_kode_unik, total_mutasi,
                            ai_model, ai_prompt_tokens, ai_completion_tokens,
                            ai_total_tokens, ai_cost_usd, ai_cost_idr
                        ) VALUES (?, ?, ?, ?, 'INPUT_STRUK', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            payload.staging_id,
                            user_id,
                            user.full_name,
                            date.today().isoformat(),
                            tab_type,
                            payload.tanggal_transaksi,
                            payload.waktu_transaksi,
                            payload.rekening_sumber_id,
                            payload.rekening_tujuan_id,
                            payload.tipe,
                            payload.kategori_id,
                            payload.penerima_pengirim,
                            payload.keterangan,
                            payload.nominal_pokok,
                            payload.biaya_admin_kode_unik,
                            payload.total_mutasi,
                            str(ai_usage.get("model") or ""),
                            int(ai_usage.get("prompt_tokens") or 0),
                            int(ai_usage.get("completion_tokens") or 0),
                            int(ai_usage.get("total_tokens") or 0),
                            float(ai_usage.get("cost_usd") or 0.0),
                            float(ai_usage.get("cost_idr") or 0.0),
                        ),
                    ).lastrowid
                    file_rows = self._insert_file_rows(
                        conn,
                        transaksi_id=transaksi_id,
                        tab_type=tab_type,
                        extracted=extracted,
                        manifest=manifest,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except Exception:
            self._restore_moved_files(moved)
            raise

        shutil.rmtree(storage_root() / "staging" / payload.staging_id, ignore_errors=True)
        reconciliation = auto_reconcile_transaction(transaksi_id)
        return {
            "staging_id": payload.staging_id,
            "transaksi_id": transaksi_id,
            "files": file_rows,
            "reconciliation": reconciliation,
            "ai_usage": ai_usage,
            "message": "Transaksi berhasil disimpan",
        }

    def _is_expired(self, expires_at: str) -> bool:
        try:
            moment = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        except ValueError:
            return True
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment < datetime.now(timezone.utc)

    def _validate_locked_fields(
        self,
        tab_type: str,
        extracted: dict,
        payload: StrukTransactionFields,
        *,
        is_cash: bool = False,
    ) -> None:
        locked = self._locked_fields(tab_type, extracted, is_cash=is_cash)
        for field in locked:
            expected = extracted.get(field)
            actual = getattr(payload, field)
            if field == "waktu_transaksi" and not expected:
                expected = "12:00:00"
            if actual != expected:
                raise StrukError(f"Field {field} terkunci oleh aturan {tab_type}")

    def _locked_fields(
        self,
        tab_type: str,
        extracted: dict,
        *,
        is_cash: bool = False,
    ) -> set[str]:
        locked: set[str] = set()
        if tab_type == "flip":
            locked.update(
                {
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening_sumber_id",
                    "tipe",
                    "nominal_pokok",
                    "biaya_admin_kode_unik",
                    "total_mutasi",
                }
            )
        elif tab_type in {"slip_gaji", "reimburse"}:
            locked.update(
                {
                    "tanggal_transaksi",
                    "waktu_transaksi",
                    "rekening_sumber_id",
                    "tipe",
                    "total_mutasi",
                    "nominal_pokok",
                }
            )
        if extracted.get("tipe") == "PINDAH_BUKU":
            locked.update(
                {
                    "tipe",
                    "kategori_id",
                    "rekening_tujuan_id",
                }
            )
        if is_cash:
            locked.update({"rekening_sumber_id", "tipe"})
            if _as_int(extracted.get("total_mutasi")) > 0:
                locked.add("total_mutasi")
        return locked

    def _recheck_hashes(self, manifest: list[dict]) -> None:
        with get_connection() as conn:
            for item in manifest:
                row = conn.execute(
                    """
                    SELECT fbl.orig_filename, ti.id AS transaksi_id
                    FROM file_bukti_log fbl
                    JOIN transaksi_internal ti ON ti.id = fbl.transaksi_internal_id
                    WHERE fbl.file_hash = ?
                    LIMIT 1
                    """,
                    (item["sha256"],),
                ).fetchone()
                if row:
                    raise StrukConflictError(
                        f"Duplikat file {row['orig_filename']} sudah tercatat pada transaksi #{row['transaksi_id']}"
                    )

    def _validate_save_payload(
        self,
        payload: StrukTransactionFields,
        tab_type: str,
        *,
        is_cash: bool = False,
        extracted: dict | None = None,
    ) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", payload.tanggal_transaksi):
            raise StrukError("Tanggal transaksi tidak valid")
        if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", payload.waktu_transaksi):
            raise StrukError("Waktu transaksi tidak valid")
        if payload.total_mutasi != payload.nominal_pokok + payload.biaya_admin_kode_unik:
            raise StrukError("Total mutasi harus sama dengan nominal pokok ditambah biaya admin/kode unik")
        with get_connection() as conn:
            source = conn.execute(
                "SELECT id, is_cash FROM rekening_perusahaan WHERE id = ? AND is_active = 1",
                (payload.rekening_sumber_id,),
            ).fetchone()
            category = conn.execute(
                "SELECT id, nama_kategori FROM kategori_sop WHERE id = ? AND is_active = 1",
                (payload.kategori_id,),
            ).fetchone()
            excluded = [
                dict(row)
                for row in conn.execute(
                    "SELECT id, nama_pemilik, potongan_no_rek, keterangan FROM rekening_dikecualikan WHERE is_active = 1"
                ).fetchall()
            ]
        if not source:
            raise StrukError("Rekening sumber tidak valid")
        if not category:
            raise StrukError("Kategori tidak valid")
        if payload.tipe == "PINDAH_BUKU":
            if payload.rekening_tujuan_id is None:
                raise StrukError("Rekening tujuan wajib diisi untuk PINDAH_BUKU")
            if payload.rekening_tujuan_id == payload.rekening_sumber_id:
                raise StrukError("Rekening sumber dan tujuan harus berbeda")
            with get_connection() as conn:
                destination = conn.execute(
                    "SELECT id FROM rekening_perusahaan WHERE id = ? AND is_active = 1",
                    (payload.rekening_tujuan_id,),
                ).fetchone()
            if not destination:
                raise StrukError("Rekening tujuan tidak valid")

        slot_a = (extracted or {}).get("slot_a") or []
        slot_b = (extracted or {}).get("slot_b") or []

        if tab_type == "normal":
            if is_cash:
                if not source["is_cash"]:
                    raise StrukError("Transaksi cash wajib menggunakan Kas Operasional")
                if payload.tipe != "KELUAR":
                    raise StrukError("Transaksi cash wajib bertipe KELUAR")
            else:
                if any(bool(row.get("is_unpaid")) for row in slot_a):
                    raise StrukError("Struk Slot A masih berstatus Belum Bayar; gunakan bukti pembayaran yang sah")
                is_incoming = payload.tipe == "MASUK"
                bad_flip = any(
                    row.get("document_type") == "flip_bank_to_fliptech"
                    or (not is_incoming and row.get("document_type") in FLIP_DOC_TYPES)
                    for row in slot_a
                )
                if bad_flip:
                    raise StrukError("Struk Flip terdeteksi di tab normal; gunakan tab flip")
                if not is_incoming and any(self._file_is_excluded(row, excluded) for row in slot_a):
                    raise StrukError("Pengirim berasal dari rekening_dikecualikan; gunakan tab reimburse")
        elif tab_type == "flip":
            if payload.tipe not in {"KELUAR", "PINDAH_BUKU"}:
                raise StrukError("Tipe transaksi Flip harus KELUAR atau PINDAH_BUKU")
            if payload.biaya_admin_kode_unik < 0 or payload.biaya_admin_kode_unik > 1000:
                raise StrukError("Selisih total mutasi dan nominal pokok Flip di luar batas Rp1.000")
        elif tab_type == "slip_gaji":
            if payload.tipe != "KELUAR":
                raise StrukError("Tipe transaksi slip gaji harus KELUAR")
            if category["nama_kategori"] not in SALARY_CATEGORIES:
                raise StrukError("Kategori slip gaji tidak diizinkan")
            if any(row.get("document_type") == "flip_to_recipient" for row in slot_b) and (
                payload.biaya_admin_kode_unik < 0 or payload.biaya_admin_kode_unik > 1000
            ):
                raise StrukError("Selisih transfer gaji via Flip di luar batas Rp1.000")
        elif tab_type == "reimburse":
            if payload.tipe != "KELUAR":
                raise StrukError("Tipe transaksi reimburse harus KELUAR")
            if any(self._file_is_excluded(row, excluded) for row in slot_b):
                raise StrukError("Pengirim Slot B berasal dari rekening_dikecualikan; reimburse diblokir")
            if abs(payload.total_mutasi - payload.nominal_pokok) > 1000:
                raise StrukError("Selisih nota awal dan transfer penggantian melebihi Rp1.000")
            if slot_a:
                nota_total = sum(_as_int(row.get("amount")) for row in slot_a)
                if abs(payload.total_mutasi - nota_total) > 1000:
                    raise StrukError("Selisih nota awal dan transfer penggantian melebihi Rp1.000")

    def _find_semantic_duplicate(self, payload: StrukSaveRequest) -> int | None:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT id FROM transaksi_internal
                WHERE tanggal_transaksi = ?
                  AND rekening_sumber_id = ?
                  AND ABS(total_mutasi - ?) <= 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (
                    payload.tanggal_transaksi,
                    payload.rekening_sumber_id,
                    payload.total_mutasi,
                ),
            ).fetchone()
        return row["id"] if row else None

    def _move_manifest_files(self, staging_id: str, manifest: list[dict]) -> list[tuple[Path, Path]]:
        moved: list[tuple[Path, Path]] = []
        staging_dir = storage_root() / "staging" / staging_id
        files_dir = storage_root() / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        try:
            for item in manifest:
                source = staging_dir / item["stored_name"]
                destination = files_dir / item["stored_name"]
                if not source.is_file():
                    raise StrukConflictError(f"File staging hilang: {item['orig_filename']}")
                if destination.exists():
                    raise StrukConflictError(f"File permanen sudah ada: {item['stored_name']}")
                source.replace(destination)
                moved.append((source, destination))
        except Exception:
            self._restore_moved_files(moved)
            raise
        return moved

    def _restore_moved_files(self, moved: list[tuple[Path, Path]]) -> None:
        for source, destination in reversed(moved):
            if destination.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                destination.replace(source)

    def _insert_file_rows(
        self,
        conn,
        *,
        transaksi_id: int,
        tab_type: str,
        extracted: dict,
        manifest: list[dict],
    ) -> list[dict]:
        rows: list[dict] = []
        for item in manifest:
            status_file = self._file_status(tab_type, item)
            tanggal_waktu = " ".join(
                part for part in [item.get("date") or "", item.get("time") or ""] if part
            )
            cursor = conn.execute(
                """
                INSERT INTO file_bukti_log (
                    transaksi_internal_id, slot, filename, orig_filename, file_hash,
                    jenis_struk, status_file, nominal_raw, tanggal_waktu_raw,
                    keterangan_raw
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaksi_id,
                    item["slot"],
                    item["stored_name"],
                    item["orig_filename"],
                    item["sha256"],
                    item.get("document_type") or extracted.get("jenis_struk") or "unknown",
                    status_file,
                    item.get("amount") or 0,
                    tanggal_waktu,
                    extracted.get("notes") or "",
                ),
            )
            rows.append(
                {
                    "id": cursor.lastrowid,
                    "slot": item["slot"],
                    "filename": item["stored_name"],
                    "status_file": status_file,
                }
            )
        return rows

    def _file_status(self, tab_type: str, item: dict) -> str:
        slot = item["slot"]
        if tab_type == "flip":
            if slot == "A":
                return "TERPAKAI_UTAMA"
            if slot == "B":
                return "TERPAKAI_PENDUKUNG_FLIP"
            return "TERPAKAI_NOTA_PENDUKUNG"
        if tab_type == "normal":
            return "TERPAKAI_UTAMA" if slot == "A" else "TERPAKAI_NOTA_PENDUKUNG"
        if tab_type in {"slip_gaji", "reimburse"}:
            return "TERPAKAI_UTAMA" if slot == "B" else "TERPAKAI_NOTA_PENDUKUNG"
        return "TERPAKAI_NOTA_PENDUKUNG"

    def list_recent(self, *, user: UserPublic, limit: int = 20) -> dict:
        user_id = self._user_id(user.username)
        where = ""
        params: list[object] = []
        if user.role == "staff":
            where = "WHERE ti.created_by_user_id = ?"
            params.append(user_id)
        params.append(limit)
        with get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    ti.id,
                    ti.staging_id,
                    ti.tanggal_input,
                    ti.tanggal_transaksi,
                    ti.waktu_transaksi,
                    ti.nama_admin,
                    ti.tab_type,
                    ti.tipe,
                    ti.rekening_sumber_id,
                    ti.rekening_tujuan_id,
                    ti.kategori_id,
                    ti.penerima_pengirim,
                    ti.keterangan,
                    ti.nominal_pokok,
                    ti.biaya_admin_kode_unik,
                    ti.total_mutasi,
                    ti.status_rekonsiliasi,
                    ti.ai_model,
                    ti.ai_prompt_tokens,
                    ti.ai_completion_tokens,
                    ti.ai_total_tokens,
                    ti.ai_cost_usd,
                    ti.ai_cost_idr,
                    ks.nama_kategori,
                    rs.kode_akun AS rekening_sumber,
                    rs.is_cash AS sumber_is_cash,
                    rt.kode_akun AS rekening_tujuan,
                    us.is_cash AS staging_is_cash,
                    us.extracted_json AS staging_extracted_json
                FROM transaksi_internal ti
                JOIN kategori_sop ks ON ks.id = ti.kategori_id
                JOIN rekening_perusahaan rs ON rs.id = ti.rekening_sumber_id
                LEFT JOIN rekening_perusahaan rt ON rt.id = ti.rekening_tujuan_id
                LEFT JOIN upload_staging us ON us.id = ti.staging_id
                {where}
                ORDER BY ti.id DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
            tx_ids = [row["id"] for row in rows]
            file_map: dict[int, list[dict]] = {tx_id: [] for tx_id in tx_ids}
            if tx_ids:
                placeholders = ",".join("?" for _ in tx_ids)
                file_rows = conn.execute(
                    f"""
                    SELECT id, transaksi_internal_id, slot, filename, orig_filename,
                           jenis_struk, status_file, nominal_raw
                    FROM file_bukti_log
                    WHERE transaksi_internal_id IN ({placeholders})
                    ORDER BY slot ASC, id ASC
                    """,
                    tuple(tx_ids),
                ).fetchall()
                for file_row in file_rows:
                    file_map[file_row["transaksi_internal_id"]].append(
                        {
                            "id": file_row["id"],
                            "slot": file_row["slot"],
                            "filename": file_row["filename"],
                            "orig_filename": file_row["orig_filename"],
                            "jenis_struk": file_row["jenis_struk"],
                            "status_file": file_row["status_file"],
                            "nominal_raw": file_row["nominal_raw"],
                            "url": f"/api/v1/struk/files/{file_row['filename']}",
                        }
                    )
        items: list[dict] = []
        for row in rows:
            item = dict(row)
            extracted = self._extracted_context_for_row(item)
            staging_cash = item.pop("staging_is_cash", None)
            sumber_cash = item.pop("sumber_is_cash", 0)
            is_cash = bool(staging_cash) if staging_cash is not None else bool(sumber_cash)
            locked = sorted(self._locked_fields(item["tab_type"], extracted, is_cash=is_cash))
            item.pop("staging_extracted_json", None)
            item.pop("staging_id", None)
            item["nominal_pokok"] = int(round(item["nominal_pokok"]))
            item["biaya_admin_kode_unik"] = int(round(item["biaya_admin_kode_unik"]))
            item["total_mutasi"] = int(round(item["total_mutasi"]))
            item["is_cash"] = is_cash
            item["locked_fields"] = locked
            item["files"] = file_map[row["id"]]
            item["ai_usage"] = {
                "model": item.pop("ai_model", "") or "",
                "prompt_tokens": int(item.pop("ai_prompt_tokens", 0) or 0),
                "completion_tokens": int(item.pop("ai_completion_tokens", 0) or 0),
                "total_tokens": int(item.pop("ai_total_tokens", 0) or 0),
                "cost_usd": round(float(item.pop("ai_cost_usd", 0) or 0.0), 8),
                "cost_idr": round(float(item.pop("ai_cost_idr", 0) or 0.0), 4),
            }
            items.append(item)
        total_tokens = sum(it["ai_usage"]["total_tokens"] for it in items)
        total_cost_usd = round(sum(it["ai_usage"]["cost_usd"] for it in items), 8)
        total_cost_idr = round(sum(it["ai_usage"]["cost_idr"] for it in items), 4)
        return {
            "items": items,
            "ai_cost_summary": {
                "total_tokens": total_tokens,
                "total_cost_usd": total_cost_usd,
                "total_cost_idr": total_cost_idr,
                "ai_tx_count": sum(1 for it in items if it["ai_usage"]["total_tokens"] > 0 or it["ai_usage"]["model"]),
            },
        }

    def _extracted_context_for_row(self, row: dict) -> dict:
        raw_json = row.get("staging_extracted_json")
        if raw_json:
            try:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict) and parsed:
                    return parsed
            except json.JSONDecodeError:
                pass
        return {
            "tanggal_transaksi": row["tanggal_transaksi"],
            "waktu_transaksi": row["waktu_transaksi"],
            "rekening": row.get("rekening_sumber"),
            "rekening_sumber_id": row["rekening_sumber_id"],
            "rekening_tujuan_id": row.get("rekening_tujuan_id"),
            "tipe": row["tipe"],
            "kategori_id": row["kategori_id"],
            "nominal_pokok": int(round(row["nominal_pokok"])),
            "biaya_admin_kode_unik": int(round(row["biaya_admin_kode_unik"])),
            "total_mutasi": int(round(row["total_mutasi"])),
            "slot_a": [],
            "slot_b": [],
            "slot_c": [],
        }

    def update(self, *, user: UserPublic, transaksi_id: int, payload: StrukUpdateRequest) -> dict:
        user_id = self._user_id(user.username)
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT ti.*, rs.kode_akun AS rekening_sumber, rs.is_cash AS sumber_is_cash,
                       us.is_cash AS staging_is_cash, us.extracted_json AS staging_extracted_json
                FROM transaksi_internal ti
                JOIN rekening_perusahaan rs ON rs.id = ti.rekening_sumber_id
                LEFT JOIN upload_staging us ON us.id = ti.staging_id
                WHERE ti.id = ?
                """,
                (transaksi_id,),
            ).fetchone()
        if not row:
            raise StrukError("Transaksi tidak ditemukan", status_code=404)
        if user.role == "staff":
            if row["created_by_user_id"] != user_id:
                raise StrukError("Staff hanya dapat mengedit transaksi miliknya", status_code=403)
            if row["status_rekonsiliasi"] != "BELUM_REKON":
                raise StrukError("Transaksi yang sudah direkonsiliasi tidak dapat diedit", status_code=403)

        row_dict = dict(row)
        tab_type = row_dict["tab_type"]
        staging_cash = row_dict.get("staging_is_cash")
        is_cash = bool(staging_cash) if staging_cash is not None else bool(row_dict.get("sumber_is_cash"))
        extracted = self._extracted_context_for_row(row_dict)

        self._validate_locked_fields(tab_type, extracted, payload, is_cash=is_cash)
        self._validate_save_payload(payload, tab_type, is_cash=is_cash, extracted=extracted)

        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            unlink_reconciliation_for_transaction(conn, transaksi_id)
            conn.execute(
                """
                UPDATE transaksi_internal
                SET tanggal_transaksi = ?,
                    waktu_transaksi = ?,
                    rekening_sumber_id = ?,
                    rekening_tujuan_id = ?,
                    tipe = ?,
                    kategori_id = ?,
                    penerima_pengirim = ?,
                    keterangan = ?,
                    nominal_pokok = ?,
                    biaya_admin_kode_unik = ?,
                    total_mutasi = ?,
                    status_rekonsiliasi = 'BELUM_REKON'
                WHERE id = ?
                """,
                (
                    payload.tanggal_transaksi,
                    payload.waktu_transaksi,
                    payload.rekening_sumber_id,
                    payload.rekening_tujuan_id,
                    payload.tipe,
                    payload.kategori_id,
                    payload.penerima_pengirim,
                    payload.keterangan,
                    payload.nominal_pokok,
                    payload.biaya_admin_kode_unik,
                    payload.total_mutasi,
                    transaksi_id,
                ),
            )
            conn.commit()

        reconciliation = auto_reconcile_transaction(transaksi_id)
        return {
            "transaksi_id": transaksi_id,
            "reconciliation": reconciliation,
            "message": "Transaksi berhasil diperbarui",
        }

    def delete(self, *, user: UserPublic, transaksi_id: int) -> dict:
        user_id = self._user_id(user.username)
        with get_connection() as conn:
            transaction = conn.execute(
                "SELECT id, created_by_user_id, status_rekonsiliasi FROM transaksi_internal WHERE id = ?",
                (transaksi_id,),
            ).fetchone()
        if not transaction:
            raise StrukError("Transaksi tidak ditemukan", status_code=404)
        if user.role == "staff":
            if transaction["created_by_user_id"] != user_id:
                raise StrukError("Staff hanya dapat menghapus transaksi miliknya", status_code=403)
            if transaction["status_rekonsiliasi"] != "BELUM_REKON":
                raise StrukError("Transaksi yang sudah direkonsiliasi tidak dapat dihapus", status_code=403)

        with get_connection() as conn:
            files = conn.execute(
                "SELECT filename FROM file_bukti_log WHERE transaksi_internal_id = ?",
                (transaksi_id,),
            ).fetchall()
            unlink_reconciliation_for_transaction(conn, transaksi_id)
            conn.execute("DELETE FROM transaksi_internal WHERE id = ?", (transaksi_id,))
            conn.commit()
        for file_row in files:
            path = storage_root() / "files" / file_row["filename"]
            path.unlink(missing_ok=True)
        return {"transaksi_id": transaksi_id, "message": "Transaksi berhasil dihapus"}

    def _user_id(self, username: str) -> int:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?",
                (username.strip().lower(),),
            ).fetchone()
        if not row:
            raise StrukError("User tidak ditemukan", status_code=401)
        return row["id"]


struk_service = StrukService()
