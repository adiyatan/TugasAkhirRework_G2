from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3
from typing import Any

from app.core.config import settings
from app.core.database import get_connection
from app.schemas.auth import UserPublic
from app.services import vision as vision_service

REPO_ROOT = Path(__file__).resolve().parents[3]
BUKTI_DIR = REPO_ROOT / "Bukti_Terstruktur_Januari_2026"

DEFAULT_USD_TO_IDR = 16000.0
CRITICAL_EVAL_FIELDS = (
    "total_mutasi",
    "nominal_pokok",
    "biaya_admin_kode_unik",
    "tanggal_transaksi",
    "rekening",
    "rekening_tujuan",
    "tipe",
)
ALL_EVAL_FIELDS = (*CRITICAL_EVAL_FIELDS, "kategori")


@dataclass(frozen=True)
class ModelCatalogItem:
    id: str
    label: str
    provider: str
    tier: str
    description: str


VISION_MODEL_CATALOG: tuple[ModelCatalogItem, ...] = (
    ModelCatalogItem(
        id="gemini/gemini-3.5-flash-lite",
        label="Gemini 3.5 Flash-Lite",
        provider="Google Gemini",
        tier="Ekonomis & Cepat (Default)",
        description="Model ringan bawaan untuk ekstraksi struk dan mutasi PDF berbiaya paling hemat.",
    ),
    ModelCatalogItem(
        id="gemini/gemini-3.8-flash",
        label="Gemini 3.8 Flash",
        provider="Google Gemini",
        tier="Flash Aktif (Seimbang)",
        description="Model Flash generasi terbaru dengan kecepatan tinggi & akurasi lebih baik dari varian Lite.",
    ),
    ModelCatalogItem(
        id="gemini/gemini-4-hydrogen",
        label="Gemini 4 Hydrogen",
        provider="Google Gemini",
        tier="Gemini 4 Efisien",
        description="Dioptimalkan untuk kecepatan, konsistensi JSON, dan ekstraksi multimodal harian.",
    ),
    ModelCatalogItem(
        id="gemini/gemini-4-argon",
        label="Gemini 4 Argon",
        provider="Google Gemini",
        tier="Gemini 4 Performa Tinggi",
        description="Model GA berkinerja tinggi untuk dokumen mutasi padat dan struk multi-lampiran.",
    ),
    ModelCatalogItem(
        id="gemini/gemini-4-carbon",
        label="Gemini 4 Carbon",
        provider="Google Gemini",
        tier="Gemini 4 Penalaran Tinggi",
        description="Penalaran multimodal kompleks untuk kasus bundle multi-penerima & rekonsiliasi sulit.",
    ),
    ModelCatalogItem(
        id="gemini/gemini-4-neon",
        label="Gemini 4 Neon",
        provider="Google Gemini",
        tier="Gemini 4 Flagship",
        description="Model Gemini 4 tingkat tertinggi untuk benchmark akurasi maksimal.",
    ),
)


@dataclass(frozen=True)
class GoldenEvalCase:
    case_id: str
    title: str
    tab_type: str
    is_cash: bool
    files: tuple[tuple[str, str], ...]  # (slot, relative_path_under_bukti_dir)
    expected: dict[str, Any]


GOLDEN_EVAL_CASES: tuple[GoldenEvalCase, ...] = (
    GoldenEvalCase(
        case_id="normal_qris_keluar",
        title="Normal QRIS Keluar — Griya Kardus Klaten",
        tab_type="normal",
        is_cash=False,
        files=(("A", "01_Normal/2026-01-06_Griya_Kardus_Klaten_70000/Slot_A_Bukti_Bayar/photo_2026-01-07_08-28-34.jpg"),),
        expected={
            "tanggal_transaksi": "2026-01-06",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Biaya-Operasional",
            "nominal_pokok": 70000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 70000,
        },
    ),
    GoldenEvalCase(
        case_id="flip_keluar",
        title="Flip Keluar + Kode Unik — Eling Muhammad Falah",
        tab_type="flip",
        is_cash=False,
        files=(
            ("A", "02_Transfer_Flip/2026-01-01_Eling_Muhammad_Falah_800353/Slot_A_Bank_to_Flip/photo_2026-01-01_16-28-57.jpg"),
            ("B", "02_Transfer_Flip/2026-01-01_Eling_Muhammad_Falah_800353/Slot_B_Flip_to_Penerima/photo_2026-01-01_16-29-59.jpg"),
        ),
        expected={
            "tanggal_transaksi": "2026-01-01",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Bahan Baku",
            "nominal_pokok": 800000,
            "biaya_admin_kode_unik": 353,
            "total_mutasi": 800353,
        },
    ),
    GoldenEvalCase(
        case_id="flip_pindah_buku",
        title="Flip Pindah Buku — BNI ke BRI Operasional",
        tab_type="flip",
        is_cash=False,
        files=(
            ("A", "02_Transfer_Flip/2026-01-17_Ilham_Nawan_Rasyid_BRI_74825/Slot_A_Bank_to_Flip/photo_2026-01-17_10-33-45.jpg"),
            ("B", "02_Transfer_Flip/2026-01-17_Ilham_Nawan_Rasyid_BRI_74825/Slot_B_Flip_to_Penerima/photo_2026-01-17_10-34-19.jpg"),
        ),
        expected={
            "tanggal_transaksi": "2026-01-17",
            "rekening": "BNI",
            "rekening_tujuan": "BRI Operasional",
            "tipe": "PINDAH_BUKU",
            "kategori": "Transfer Antar Rekening (Pindah Buku)",
            "nominal_pokok": 74500,
            "biaya_admin_kode_unik": 325,
            "total_mutasi": 74825,
        },
    ),
    GoldenEvalCase(
        case_id="reimburse_keluar",
        title="Reimburse Nota + Transfer — Muhamad Ali Shodiqi",
        tab_type="reimburse",
        is_cash=False,
        files=(
            ("A", "04_Reimburse/2026-01-17_Muhamad_Ali_Shodiqi_Reim_75000/Slot_A_Nota_Awal/photo_2026-01-17_10-37-42.jpg"),
            ("B", "04_Reimburse/2026-01-17_Muhamad_Ali_Shodiqi_Reim_75000/Slot_B_Bukti_Reimburse/photo_2026-01-17_10-41-34.jpg"),
        ),
        expected={
            "tanggal_transaksi": "2026-01-17",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Biaya-Perlengkapan Kantor dan Administrasi",
            "nominal_pokok": 75000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 75000,
        },
    ),
    GoldenEvalCase(
        case_id="normal_masuk",
        title="Normal Masuk — DP Workshop Retno Palupi",
        tab_type="normal",
        is_cash=False,
        files=(("A", "01_Normal/2026-01-06_Masuk_Retno_Palupi_Bank_Jatim_2115000/Slot_A_Bukti_Bayar/photo_2026-01-06_09-27-39.jpg"),),
        expected={
            "tanggal_transaksi": "2026-01-06",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "MASUK",
            "kategori": "Pendapatan Usaha (Workshop)",
            "nominal_pokok": 2115000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 2115000,
        },
    ),
    GoldenEvalCase(
        case_id="normal_pindah_buku",
        title="Normal Pindah Buku — Bank Jago ke BNI",
        tab_type="normal",
        is_cash=False,
        files=(("A", "01_Normal/2026-01-01_PindahBuku_Bank_Jago_Syariah_BNI_210000/Slot_A_Bukti_Bayar/photo_2026-01-01_17-06-05.jpg"),),
        expected={
            "tanggal_transaksi": "2026-01-01",
            "rekening": "Bank Jago (Kantong 1)",
            "rekening_tujuan": "BNI",
            "tipe": "PINDAH_BUKU",
            "kategori": "Transfer Antar Rekening (Pindah Buku)",
            "nominal_pokok": 210000,
            "biaya_admin_kode_unik": 0,
            "total_mutasi": 210000,
        },
    ),
    GoldenEvalCase(
        case_id="slip_gaji_keluar",
        title="Slip Gaji + Flip — Nita Repi Jayanti",
        tab_type="slip_gaji",
        is_cash=False,
        files=(
            ("A", "03_Slip_Gaji/2026-01-02_Nita_Repi_Jayanti_1129075/Slot_A_Slip_Gaji/photo_2026-01-02_11-17-59.jpg"),
            ("B", "03_Slip_Gaji/2026-01-02_Nita_Repi_Jayanti_1129075/Slot_B_Bukti_Transfer/photo_2026-01-02_11-20-19.jpg"),
            ("B", "03_Slip_Gaji/2026-01-02_Nita_Repi_Jayanti_1129075/Slot_B_Bukti_Transfer/photo_2026-01-02_11-20-56.jpg"),
        ),
        expected={
            "tanggal_transaksi": "2026-01-02",
            "rekening": "BNI",
            "rekening_tujuan": None,
            "tipe": "KELUAR",
            "kategori": "Biaya-Gaji Karyawan",
            "nominal_pokok": 1128750,
            "biaya_admin_kode_unik": 325,
            "total_mutasi": 1129075,
        },
    ),
)


class AiServiceError(Exception):
    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


def _user_id(conn: sqlite3.Connection, username: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM users WHERE username = ?",
        (username.strip().lower(),),
    ).fetchone()
    return int(row["id"]) if row else None


def get_ai_config_row() -> tuple[str, float, str, str]:
    """Return (active_model, usd_to_idr_rate, updated_by_username, updated_at)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT active_vision_model, usd_to_idr_rate, updated_by_username, updated_at FROM ai_config WHERE id = 1"
        ).fetchone()
    if not row:
        return settings.vision_model, DEFAULT_USD_TO_IDR, "system", ""
    active_model = (row["active_vision_model"] or "").strip() or settings.vision_model
    rate = float(row["usd_to_idr_rate"] or DEFAULT_USD_TO_IDR)
    return active_model, rate, row["updated_by_username"] or "system", row["updated_at"] or ""


def get_active_vision_model() -> str:
    """Return the active vision model configured by management or fallback to settings."""
    model, _, _, _ = get_ai_config_row()
    return model


def get_usd_to_idr_rate() -> float:
    _, rate, _, _ = get_ai_config_row()
    return rate


def build_usage_payload(
    raw_usage: dict[str, Any] | None,
    *,
    model: str | None = None,
    used_ai: bool = True,
    pages_processed: int = 1,
    rate: float | None = None,
) -> dict[str, Any]:
    """Normalize token usage & USD/IDR cost dictionary for API responses and persistence."""
    usd_to_idr = float(rate if rate is not None else get_usd_to_idr_rate())
    active_model = model or get_active_vision_model()
    if not used_ai:
        return {
            "used_ai": False,
            "model": model or "Deterministik",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "cost_idr": 0.0,
            "usd_to_idr_rate": usd_to_idr,
            "cost_source": "deterministic",
            "latency_ms": 0,
            "pages_processed": pages_processed,
        }

    usage = raw_usage or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    used_model = str(usage.get("model") or active_model)
    cost_usd = float(usage.get("cost_usd") or 0.0)
    cost_source = str(usage.get("cost_source") or "estimate")
    if cost_usd <= 0.0 and (prompt_tokens > 0 or completion_tokens > 0):
        cost_usd = vision_service.estimate_model_cost(used_model, prompt_tokens, completion_tokens)
        cost_source = "catalog_estimate"
    cost_idr = round(cost_usd * usd_to_idr, 4)

    return {
        "used_ai": True,
        "model": used_model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cost_usd": round(cost_usd, 8),
        "cost_idr": cost_idr,
        "usd_to_idr_rate": usd_to_idr,
        "cost_source": cost_source,
        "latency_ms": int(usage.get("latency_ms") or 0),
        "pages_processed": pages_processed,
    }


def record_ai_usage(
    *,
    feature: str,
    usage: dict[str, Any],
    user_id: int | None = None,
    reference_type: str = "",
    reference_id: str | int = "",
) -> None:
    """Persist one AI usage record into ai_usage_log when AI was invoked."""
    if not usage or not usage.get("used_ai", True):
        return
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO ai_usage_log (
                feature, reference_type, reference_id, user_id,
                model, prompt_tokens, completion_tokens, total_tokens,
                cost_usd, cost_idr, latency_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feature,
                reference_type,
                str(reference_id),
                user_id,
                str(usage.get("model") or ""),
                int(usage.get("prompt_tokens") or 0),
                int(usage.get("completion_tokens") or 0),
                int(usage.get("total_tokens") or 0),
                float(usage.get("cost_usd") or 0.0),
                float(usage.get("cost_idr") or 0.0),
                int(usage.get("latency_ms") or 0),
            ),
        )
        conn.commit()


def _model_catalog_with_pricing(usd_to_idr: float) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in VISION_MODEL_CATALOG:
        inp, out = vision_service.get_model_pricing(item.id)
        inp_1m_usd = round(inp * 1_000_000, 4)
        out_1m_usd = round(out * 1_000_000, 4)
        items.append(
            {
                "id": item.id,
                "label": item.label,
                "provider": item.provider,
                "tier": item.tier,
                "description": item.description,
                "input_cost_per_1m_usd": inp_1m_usd,
                "output_cost_per_1m_usd": out_1m_usd,
                "input_cost_per_1m_idr": round(inp_1m_usd * usd_to_idr, 2),
                "output_cost_per_1m_idr": round(out_1m_usd * usd_to_idr, 2),
            }
        )
    return items


def _eval_run_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "candidate_model": row["candidate_model"],
        "baseline_model": row["baseline_model"],
        "sample_count": int(row["sample_count"]),
        "status": row["status"],
        "gate_decision": row["gate_decision"],
        "summary": json.loads(row["summary_json"] or "{}"),
        "details": json.loads(row["details_json"] or "[]"),
        "created_at": row["created_at"],
    }


def _normalize_compare_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(round(float(value)))
    return str(value).strip()


async def _run_model_on_cases(
    *,
    model: str,
    cases: list[GoldenEvalCase],
    usd_to_idr: float,
) -> dict[str, Any]:
    from app.services.struk_service import (  # lazy import to avoid circular dependency
        _loads_json,
        _validate_payload,
        render_prompt,
        struk_service,
    )

    metadata = struk_service.get_metadata()
    case_results: list[dict[str, Any]] = []
    field_hits = {field: 0 for field in ALL_EVAL_FIELDS}
    schema_valid_count = 0
    rule_pass_count = 0
    critical_pass_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    total_cost_usd = 0.0
    total_cost_idr = 0.0
    total_latency_ms = 0

    for case in cases:
        images: list[vision_service.VisionImage] = []
        for slot, rel_path in case.files:
            file_path = BUKTI_DIR / rel_path
            if not file_path.is_file():
                raise AiServiceError(
                    f"File golden dataset tidak ditemukan: {rel_path}",
                    status_code=500,
                )
            images.append(
                vision_service.VisionImage(
                    slot=slot,
                    filename=file_path.name,
                    content_type="image/jpeg",
                    data=file_path.read_bytes(),
                )
            )

        prompt = render_prompt(case.tab_type, case.is_cash, metadata)
        vision_service.reset_last_vision_usage()
        schema_valid = False
        rule_pass = False
        error_msg = ""
        extracted: dict[str, Any] = {}
        rule_errors: list[str] = []

        try:
            raw = await vision_service.complete_vision(
                model=model,
                prompt=prompt,
                images=images,
                response_format={"type": "json_object"},
                api_key=settings.vision_api_key or None,
            )
            usage = build_usage_payload(
                vision_service.consume_last_vision_usage(),
                model=model,
                used_ai=True,
                pages_processed=len(images),
                rate=usd_to_idr,
            )
            payload = _loads_json(raw)
            expected_counts = {
                "slot_a": sum(1 for slot, _ in case.files if slot == "A"),
                "slot_b": sum(1 for slot, _ in case.files if slot == "B"),
                "slot_c": sum(1 for slot, _ in case.files if slot == "C"),
            }
            _validate_payload(payload, expected_counts)
            schema_valid = True
            extracted, rule_errors, _, _ = struk_service._apply_rules(
                tab_type=case.tab_type,
                is_cash=case.is_cash,
                payload=payload,
                metadata=metadata,
            )
            rule_pass = len(rule_errors) == 0
        except Exception as exc:
            usage = build_usage_payload(
                vision_service.consume_last_vision_usage(),
                model=model,
                used_ai=True,
                pages_processed=len(images),
                rate=usd_to_idr,
            )
            error_msg = str(exc)

        field_comparisons: dict[str, dict[str, Any]] = {}
        matched_fields = 0
        critical_matched = True
        for field in ALL_EVAL_FIELDS:
            expected_val = _normalize_compare_value(case.expected.get(field))
            actual_val = _normalize_compare_value(extracted.get(field)) if schema_valid else None
            is_match = schema_valid and (expected_val == actual_val)
            if is_match:
                field_hits[field] += 1
                matched_fields += 1
            elif field in CRITICAL_EVAL_FIELDS:
                critical_matched = False
            field_comparisons[field] = {
                "expected": case.expected.get(field),
                "actual": extracted.get(field) if schema_valid else None,
                "match": is_match,
            }

        critical_pass = schema_valid and rule_pass and critical_matched
        if schema_valid:
            schema_valid_count += 1
        if rule_pass:
            rule_pass_count += 1
        if critical_pass:
            critical_pass_count += 1

        total_prompt_tokens += usage["prompt_tokens"]
        total_completion_tokens += usage["completion_tokens"]
        total_tokens += usage["total_tokens"]
        total_cost_usd += usage["cost_usd"]
        total_cost_idr += usage["cost_idr"]
        total_latency_ms += usage["latency_ms"]

        case_results.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "tab_type": case.tab_type,
                "schema_valid": schema_valid,
                "rule_pass": rule_pass,
                "rule_errors": rule_errors,
                "critical_pass": critical_pass,
                "field_accuracy_pct": round((matched_fields / len(ALL_EVAL_FIELDS)) * 100, 1),
                "fields": field_comparisons,
                "error": error_msg,
                "usage": usage,
            }
        )

    n = len(cases)
    schema_validity_pct = round((schema_valid_count / n) * 100, 1)
    rule_pass_pct = round((rule_pass_count / n) * 100, 1)
    critical_pass_pct = round((critical_pass_count / n) * 100, 1)
    field_accuracy_map = {
        field: round((hits / n) * 100, 1) for field, hits in field_hits.items()
    }
    overall_field_accuracy_pct = round(
        sum(field_accuracy_map.values()) / len(ALL_EVAL_FIELDS), 1
    )

    return {
        "model": model,
        "sample_count": n,
        "schema_validity_pct": schema_validity_pct,
        "rule_pass_pct": rule_pass_pct,
        "critical_pass_pct": critical_pass_pct,
        "overall_field_accuracy_pct": overall_field_accuracy_pct,
        "field_accuracy": field_accuracy_map,
        "avg_latency_ms": int(round(total_latency_ms / n)),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost_usd, 8),
        "total_cost_idr": round(total_cost_idr, 4),
        "avg_cost_idr_per_receipt": round(total_cost_idr / n, 4),
        "cases": case_results,
    }


def _gate_decision(
    *,
    candidate_metrics: dict[str, Any],
    regressions: list[str],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    schema_pct = candidate_metrics["schema_validity_pct"]
    critical_pct = candidate_metrics["critical_pass_pct"]
    rule_pct = candidate_metrics["rule_pass_pct"]

    if schema_pct < 80.0 or critical_pct < 60.0 or len(regressions) > 0:
        if schema_pct < 80.0:
            reasons.append(f"Schema JSON valid hanya {schema_pct}% (< 80%).")
        if critical_pct < 60.0:
            reasons.append(f"Akurasi field finansial kritis hanya {critical_pct}% (< 60%).")
        if regressions:
            reasons.append(
                f"Terjadi regresi pada {len(regressions)} kasus yang sebelumnya lulus di baseline ({', '.join(regressions)})."
            )
        return "FAIL", reasons

    if schema_pct == 100.0 and critical_pct >= 80.0 and rule_pct >= 80.0:
        reasons.append(
            f"Skema JSON 100% valid, akurasi finansial kritis {critical_pct}%, dan nol regresi terhadap baseline."
        )
        return "PASS", reasons

    reasons.append(
        f"Skema valid {schema_pct}% dan akurasi kritis {critical_pct}% — tinjau detail kasus sebelum promosi."
    )
    return "WARNING", reasons


class AiService:
    """Service untuk manajemen model AI, pelacakan token/cost, dan evaluasi sistem AI."""

    def get_overview(self) -> dict[str, Any]:
        active_model, usd_to_idr, updated_by, updated_at = get_ai_config_row()
        catalog = _model_catalog_with_pricing(usd_to_idr)
        active_meta = next((m for m in catalog if m["id"] == active_model), None)
        if active_meta is None:
            inp, out = vision_service.get_model_pricing(active_model)
            inp_1m = round(inp * 1_000_000, 4)
            out_1m = round(out * 1_000_000, 4)
            active_meta = {
                "id": active_model,
                "label": active_model,
                "provider": active_model.split("/", 1)[0] if "/" in active_model else "Custom",
                "tier": "Custom Model",
                "description": "Model kustom yang dikonfigurasi langsung melalui LiteLLM.",
                "input_cost_per_1m_usd": inp_1m,
                "output_cost_per_1m_usd": out_1m,
                "input_cost_per_1m_idr": round(inp_1m * usd_to_idr, 2),
                "output_cost_per_1m_idr": round(out_1m * usd_to_idr, 2),
            }

        with get_connection() as conn:
            totals_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_calls,
                    COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                    COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_idr), 0) AS cost_idr
                FROM ai_usage_log
                """
            ).fetchone()
            feature_rows = conn.execute(
                """
                SELECT
                    feature,
                    COUNT(*) AS calls,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(cost_usd), 0) AS cost_usd,
                    COALESCE(SUM(cost_idr), 0) AS cost_idr
                FROM ai_usage_log
                GROUP BY feature
                ORDER BY feature ASC
                """
            ).fetchall()
            eval_rows = conn.execute(
                "SELECT * FROM ai_eval_runs ORDER BY id DESC LIMIT 15"
            ).fetchall()

        by_feature = {
            row["feature"]: {
                "calls": int(row["calls"]),
                "total_tokens": int(row["total_tokens"]),
                "cost_usd": round(float(row["cost_usd"]), 8),
                "cost_idr": round(float(row["cost_idr"]), 4),
            }
            for row in feature_rows
        }
        eval_runs = [_eval_run_row_to_dict(row) for row in eval_rows]

        latest_pass_models = {
            run["candidate_model"] for run in eval_runs if run["gate_decision"] == "PASS"
        }

        return {
            "active_model": active_meta,
            "usd_to_idr_rate": usd_to_idr,
            "updated_by": updated_by,
            "updated_at": updated_at,
            "api_key_configured": bool((settings.vision_api_key or "").strip()),
            "catalog": [
                {**item, "evaluated_pass": item["id"] in latest_pass_models}
                for item in catalog
            ],
            "usage_summary": {
                "total_calls": int(totals_row["total_calls"]),
                "prompt_tokens": int(totals_row["prompt_tokens"]),
                "completion_tokens": int(totals_row["completion_tokens"]),
                "total_tokens": int(totals_row["total_tokens"]),
                "cost_usd": round(float(totals_row["cost_usd"]), 8),
                "cost_idr": round(float(totals_row["cost_idr"]), 4),
                "by_feature": by_feature,
            },
            "golden_dataset": [
                {
                    "case_id": case.case_id,
                    "title": case.title,
                    "tab_type": case.tab_type,
                    "file_count": len(case.files),
                    "expected": case.expected,
                }
                for case in GOLDEN_EVAL_CASES
            ],
            "evaluations": eval_runs,
        }

    def switch_model(
        self,
        *,
        user: UserPublic,
        model: str,
        usd_to_idr_rate: float | None = None,
    ) -> dict[str, Any]:
        cleaned = model.strip()
        if not cleaned or any(ch.isspace() for ch in cleaned):
            raise AiServiceError("Nama model tidak boleh kosong atau mengandung spasi")
        current_rate = get_usd_to_idr_rate()
        next_rate = float(usd_to_idr_rate) if usd_to_idr_rate is not None else current_rate

        with get_connection() as conn:
            conn.execute(
                """
                UPDATE ai_config
                SET active_vision_model = ?,
                    usd_to_idr_rate = ?,
                    updated_by_username = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (cleaned, next_rate, user.username),
            )
            conn.commit()

        overview = self.get_overview()
        return {
            "message": f"Model AI aktif berhasil dipindahkan ke {cleaned}",
            "active_model": overview["active_model"],
            "usd_to_idr_rate": overview["usd_to_idr_rate"],
        }

    async def evaluate_model(
        self,
        *,
        user: UserPublic,
        candidate_model: str,
        sample_size: int = 4,
        compare_baseline: bool = True,
    ) -> dict[str, Any]:
        cleaned_candidate = candidate_model.strip()
        if not cleaned_candidate or any(ch.isspace() for ch in cleaned_candidate):
            raise AiServiceError("Nama model kandidat tidak valid")

        baseline_model, usd_to_idr, _, _ = get_ai_config_row()
        selected_cases = list(GOLDEN_EVAL_CASES[: max(1, min(sample_size, len(GOLDEN_EVAL_CASES)))])

        candidate_metrics = await _run_model_on_cases(
            model=cleaned_candidate,
            cases=selected_cases,
            usd_to_idr=usd_to_idr,
        )

        baseline_metrics: dict[str, Any] | None = None
        regressions: list[str] = []
        improvements: list[str] = []
        comparison: dict[str, Any] | None = None

        run_baseline = compare_baseline and cleaned_candidate != baseline_model
        if run_baseline:
            baseline_metrics = await _run_model_on_cases(
                model=baseline_model,
                cases=selected_cases,
                usd_to_idr=usd_to_idr,
            )
            base_by_id = {c["case_id"]: c for c in baseline_metrics["cases"]}
            for cand_case in candidate_metrics["cases"]:
                base_case = base_by_id.get(cand_case["case_id"])
                if not base_case:
                    continue
                if base_case["critical_pass"] and not cand_case["critical_pass"]:
                    regressions.append(cand_case["case_id"])
                elif not base_case["critical_pass"] and cand_case["critical_pass"]:
                    improvements.append(cand_case["case_id"])

            comparison = {
                "baseline_model": baseline_model,
                "baseline_critical_pass_pct": baseline_metrics["critical_pass_pct"],
                "baseline_field_accuracy_pct": baseline_metrics["overall_field_accuracy_pct"],
                "baseline_avg_latency_ms": baseline_metrics["avg_latency_ms"],
                "baseline_total_cost_idr": baseline_metrics["total_cost_idr"],
                "delta_critical_pass_pct": round(
                    candidate_metrics["critical_pass_pct"] - baseline_metrics["critical_pass_pct"], 1
                ),
                "delta_field_accuracy_pct": round(
                    candidate_metrics["overall_field_accuracy_pct"] - baseline_metrics["overall_field_accuracy_pct"],
                    1,
                ),
                "delta_latency_ms": candidate_metrics["avg_latency_ms"] - baseline_metrics["avg_latency_ms"],
                "delta_cost_idr": round(
                    candidate_metrics["total_cost_idr"] - baseline_metrics["total_cost_idr"], 4
                ),
                "regressions": regressions,
                "improvements": improvements,
            }

        gate_decision, gate_reasons = _gate_decision(
            candidate_metrics=candidate_metrics,
            regressions=regressions,
        )
        run_status = "COMPLETED" if candidate_metrics["schema_validity_pct"] > 0 else "FAILED"

        summary_payload = {
            "candidate_model": cleaned_candidate,
            "baseline_model": baseline_model,
            "sample_count": len(selected_cases),
            "gate_decision": gate_decision,
            "gate_reasons": gate_reasons,
            "schema_validity_pct": candidate_metrics["schema_validity_pct"],
            "rule_pass_pct": candidate_metrics["rule_pass_pct"],
            "critical_pass_pct": candidate_metrics["critical_pass_pct"],
            "overall_field_accuracy_pct": candidate_metrics["overall_field_accuracy_pct"],
            "field_accuracy": candidate_metrics["field_accuracy"],
            "avg_latency_ms": candidate_metrics["avg_latency_ms"],
            "total_tokens": candidate_metrics["total_tokens"],
            "total_cost_usd": candidate_metrics["total_cost_usd"],
            "total_cost_idr": candidate_metrics["total_cost_idr"],
            "avg_cost_idr_per_receipt": candidate_metrics["avg_cost_idr_per_receipt"],
            "comparison": comparison,
        }

        with get_connection() as conn:
            uid = _user_id(conn, user.username)
            cur = conn.execute(
                """
                INSERT INTO ai_eval_runs (
                    candidate_model, baseline_model, sample_count,
                    status, gate_decision, summary_json, details_json, created_by_user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cleaned_candidate,
                    baseline_model,
                    len(selected_cases),
                    run_status,
                    gate_decision,
                    json.dumps(summary_payload, ensure_ascii=False),
                    json.dumps(candidate_metrics["cases"], ensure_ascii=False),
                    uid,
                ),
            )
            run_id = int(cur.lastrowid)
            conn.commit()

        # Log cumulative evaluation token cost for candidate (+ baseline if executed)
        record_ai_usage(
            feature="ai_eval",
            usage={
                "used_ai": True,
                "model": cleaned_candidate,
                "prompt_tokens": candidate_metrics["total_prompt_tokens"],
                "completion_tokens": candidate_metrics["total_completion_tokens"],
                "total_tokens": candidate_metrics["total_tokens"],
                "cost_usd": candidate_metrics["total_cost_usd"],
                "cost_idr": candidate_metrics["total_cost_idr"],
                "latency_ms": candidate_metrics["avg_latency_ms"],
            },
            user_id=uid,
            reference_type="eval_run",
            reference_id=run_id,
        )
        if baseline_metrics is not None:
            record_ai_usage(
                feature="ai_eval",
                usage={
                    "used_ai": True,
                    "model": baseline_model,
                    "prompt_tokens": baseline_metrics["total_prompt_tokens"],
                    "completion_tokens": baseline_metrics["total_completion_tokens"],
                    "total_tokens": baseline_metrics["total_tokens"],
                    "cost_usd": baseline_metrics["total_cost_usd"],
                    "cost_idr": baseline_metrics["total_cost_idr"],
                    "latency_ms": baseline_metrics["avg_latency_ms"],
                },
                user_id=uid,
                reference_type="eval_run_baseline",
                reference_id=run_id,
            )

        return {
            "id": run_id,
            "candidate_model": cleaned_candidate,
            "baseline_model": baseline_model,
            "sample_count": len(selected_cases),
            "status": run_status,
            "gate_decision": gate_decision,
            "summary": summary_payload,
            "details": candidate_metrics["cases"],
            "baseline_details": baseline_metrics["cases"] if baseline_metrics else None,
        }

    def list_evaluations(self, *, limit: int = 20) -> dict[str, Any]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ai_eval_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {"items": [_eval_run_row_to_dict(row) for row in rows]}

    def get_evaluation(self, *, run_id: int) -> dict[str, Any]:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM ai_eval_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
        if not row:
            raise AiServiceError("Riwayat evaluasi tidak ditemukan", status_code=404)
        return _eval_run_row_to_dict(row)


ai_service = AiService()
