"""Unit tests for all 12 Presentation Enhancements."""

import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.orchestrator.presets import PRESETS

client = TestClient(app)
SAMPLE_PARAMS = PRESETS[0]["data"]


@pytest.fixture
def sample_calc_result():
    return {
        "status": "success",
        "ipr": {"q_liq": [139.98, 0.0], "p_wf": [1.0, 200.0]},
        "vlp": {"q_liq": [0.0, 400.0], "p_wf": [48.19, 62.66]},
        "operating_point": {"q_liq": 127.78, "p_wf": 50.27},
        "meta": {"calc_time_ms": 25.0}
    }


def test_enhancement_05_reports(sample_calc_result):
    """05. Проверка генерации Markdown и Excel отчетов."""
    # Markdown
    resp = client.post("/api/enhancements/report/markdown", json={
        "well_name": "Тестовая скважина",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "Тестовая скважина" in data["markdown"]
    assert "127.78" in data["markdown"]

    # Excel
    resp_xls = client.post("/api/enhancements/report/excel", json={
        "well_name": "Тестовая скважина",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp_xls.status_code == 200
    assert resp_xls.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(resp_xls.content) > 1000

    # HTML
    resp_html = client.post("/api/enhancements/report/html", json={
        "well_name": "Тестовая скважина",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp_html.status_code == 200
    assert "text/html" in resp_html.headers["content-type"]
    assert "Паспорт узлового анализа" in resp_html.text
    assert "<svg" in resp_html.text
    assert "127.78" in resp_html.text

    # CSV
    resp_csv = client.post("/api/enhancements/report/csv", json={
        "well_name": "Тестовая скважина",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp_csv.status_code == 200
    assert "text/csv" in resp_csv.headers["content-type"]
    assert "127.78" in resp_csv.text

    # JSON
    resp_json = client.post("/api/enhancements/report/json", json={
        "well_name": "Тестовая скважина",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp_json.status_code == 200
    js = resp_json.json()
    assert js["well_name"] == "Тестовая скважина"
    assert js["key_metrics"]["q_liq_m3_day"] == 127.78
    assert js["key_metrics"]["p_wf_atm"] == 50.27


def test_enhancement_06_folder_scan(tmp_path):
    """06. Проверка сканирования указанной папки с авто-парсингом файлов."""
    test_file = tmp_path / "well_alpha.txt"
    test_file.write_text("p_res: 195\nwct: 45\npi: 1.1\npb: 145\np_wh: 12\nh_res: 1550\nh_mes: 1100\ntubing.d: 0.062\ncasing.d: 0.12\nMD: [0, 1000, 1550]\nTVD: [0, 1000, 1200]\npvt.rp: 90\npvt.gamma_oil: 0.82\npvt.gamma_gas: 0.7\npvt.gamma_wat: 1.0\npvt.t_res: 85")

    resp = client.post("/api/enhancements/scan", json={"folder_path": str(tmp_path), "recursive": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["total_files_found"] == 1
    assert data["wells"][0]["filename"] == "well_alpha.txt"


def test_enhancement_09_optimization(monkeypatch):
    """09. Проверка подбора параметров режима (НКТ, устьевое давление, WCT_crit)."""
    async def mock_calc(params):
        d = params.get("vlp", {}).get("tubing", {}).get("d", 0.062)
        q = 130.0 if d > 0.06 else 115.0
        return {"operating_point": {"q_liq": q, "p_wf": 50.0}}

    from app.enhancements import router as enh_mod
    monkeypatch.setattr(enh_mod, "_calc_wrapper", mock_calc)

    resp = client.post("/api/enhancements/optimize", json={
        "params": SAMPLE_PARAMS,
        "optimization_type": "all"
    })
    assert resp.status_code == 200
    data = resp.json()["results"]
    assert "tubing_optimization" in data
    assert "wellhead_sensitivity" in data
    assert "critical_wct" in data


def test_enhancement_10_matching(monkeypatch):
    """10. Проверка сравнения с фактическим замером (History Matching)."""
    async def mock_calc(params):
        return {"operating_point": {"q_liq": 127.78, "p_wf": 50.27}}

    from app.enhancements import router as enh_mod
    monkeypatch.setattr(enh_mod, "_calc_wrapper", mock_calc)

    resp = client.post("/api/enhancements/match", json={
        "params": SAMPLE_PARAMS,
        "measured_q_liq": 115.0,
        "measured_p_wf": 55.0
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["comparison"]["deltas"]["delta_q_liq_m3_day"] == -12.78
    assert len(data["diagnosis"]) > 0


def test_enhancement_11_meeting_protocol():
    """11. Проверка генерации протокола технического совещания."""
    sample_text = """
    Совещание по скважине № 102
    Присутствовали: Главный геолог Смирнов, Технолог ЦДНГ Петров
    Повестка: рост обводненности до 60%, падение дебита
    Решили: провести промывку НКТ от парафина и скорректировать штуцер
    Ответственный: мастер участка, срок до 28 ноября
    """
    resp = client.post("/api/enhancements/protocol", json={"transcript": sample_text})
    assert resp.status_code == 200
    data = resp.json()
    assert data["well_name"] == "102"
    assert "ПРОТОКОЛ ТЕХНИЧЕСКОГО СОВЕЩАНИЯ" in data["protocol_markdown"]


def test_enhancement_12_batch(monkeypatch):
    """12. Проверка пакетного расчета фонда скважин и выгрузки Excel."""
    async def mock_calc(params):
        return {"operating_point": {"q_liq": 100.0, "p_wf": 45.0}}

    from app.enhancements import router as enh_mod
    monkeypatch.setattr(enh_mod, "_calc_wrapper", mock_calc)

    wells_pool = [
        {"id": "w1", "name": "Скважина 1", "params": SAMPLE_PARAMS},
        {"id": "w2", "name": "Скважина 2", "params": SAMPLE_PARAMS}
    ]

    resp = client.post("/api/enhancements/batch", json={"wells": wells_pool})
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"]["total_wells"] == 2
    assert data["summary"]["total_q_liq_m3_day"] == 200.0

    # Excel export
    resp_xls = client.post("/api/enhancements/batch/excel", json={"wells": wells_pool})
    assert resp_xls.status_code == 200
    assert resp_xls.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(resp_xls.content) > 1000


def test_enhancement_02_vision_offline():
    """02. Проверка оптического распознавания паспорта (честный отказ на пустой картинке и OCR по тексту)."""
    import io
    import shutil
    from PIL import Image, ImageDraw

    dummy_img = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
    resp = client.post(
        "/api/enhancements/vision",
        files={"file": ("blank.png", dummy_img, "image/png")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] in {"not_found", "unavailable"}
    assert data["extracted_params"] == {}

    if shutil.which("tesseract"):
        from PIL import ImageFont

        try:
            font = ImageFont.load_default(size=28)
        except TypeError:
            font = ImageFont.load_default()
        img = Image.new("RGB", (600, 220), "white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "p_res: 215 atm\n", fill="black", font=font)
        draw.text((20, 90), "wct: 40 %\n", fill="black", font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        resp2 = client.post(
            "/api/enhancements/vision",
            files={"file": ("passport_real.png", buf.getvalue(), "image/png")}
        )
        assert resp2.status_code == 200
        d2 = resp2.json()
        assert d2["status"] == "success"
        assert d2["extracted_params"]["ipr"]["p_res"] == 215.0


def test_enhancement_03_audio_offline():
    """03. Проверка голосового ввода."""
    dummy_audio = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    resp = client.post(
        "/api/enhancements/audio",
        files={"file": ("voice_command.wav", dummy_audio, "audio/wav")}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "transcript" in data


def test_killer_01_unit_economics(sample_calc_result):
    """Killer 1: Проверка юнит-экономики и срока окупаемости."""
    opt_result = {
        "status": "success",
        "operating_point": {"q_liq": 142.1, "p_wf": 44.0}
    }
    resp = client.post("/api/enhancements/economics", json={
        "base_params": SAMPLE_PARAMS,
        "base_result": sample_calc_result,
        "opt_params": SAMPLE_PARAMS,
        "opt_result": opt_result,
        "oil_price_rub": 35000.0,
        "ndpi_rub": 18000.0,
        "transport_rub": 2500.0,
        "water_treatment_rub": 150.0,
        "workover_cost_rub": 1800000.0
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["deltas"]["delta_q_oil_tons_day"] > 0
    assert data["deltas"]["delta_daily_profit_rub"] > 0
    assert "payback_period_days" in data["deltas"]
    assert "executive_summary" in data


def test_killer_02_flow_assurance(sample_calc_result):
    """Killer 2: Проверка критерия Тернера и API RP 14E."""
    resp = client.post("/api/enhancements/flow-assurance", json={
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "turner_liquid_loading" in data
    assert "critical_turner_velocity_m_s" in data["turner_liquid_loading"]
    assert "api_14e_erosion" in data
    assert "erosional_velocity_limit_m_s" in data["api_14e_erosion"]


def test_killer_03_vfm(monkeypatch):
    """Killer 3: Проверка виртуального расходомера."""
    async def mock_calc(params):
        return {"operating_point": {"q_liq": 122.5, "p_wf": 51.0}}

    from app.enhancements import router as enh_mod
    monkeypatch.setattr(enh_mod, "_calc_wrapper", mock_calc)

    resp = client.post("/api/enhancements/vfm", json={
        "params": SAMPLE_PARAMS,
        "p_wh_observed": 12.0,
        "t_wh_observed": 25.0
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["virtual_meter_reading"]["q_liq_estimated_m3_day"] == 122.5
    assert data["virtual_meter_reading"]["confidence_percent"] > 90


def test_killer_04_monte_carlo(monkeypatch):
    """Killer 4: Проверка анализа неопределенностей Монте-Карло (P10/P50/P90)."""
    async def mock_calc(params):
        pres = float(params.get("p_res") or 200.0)
        return {"operating_point": {"q_liq": 100.0 + (pres - 200.0) * 0.5, "p_wf": 50.0}}

    from app.enhancements import router as enh_mod
    monkeypatch.setattr(enh_mod, "_calc_wrapper", mock_calc)

    resp = client.post("/api/enhancements/monte-carlo", json={
        "params": SAMPLE_PARAMS,
        "n_iterations": 50,
        "p_res_std_pct": 5.0,
        "pi_std_pct": 10.0,
        "seed": 42
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "percentiles" in data
    assert data["percentiles"]["P90_conservative_m3_day"] <= data["percentiles"]["P50_most_likely_m3_day"]
    assert data["percentiles"]["P50_most_likely_m3_day"] <= data["percentiles"]["P10_optimistic_m3_day"]
    assert len(data["histogram"]) == 10


def test_killer_05_gtm_generator(sample_calc_result):
    """Killer 5: Проверка авто-генерации заявки на ГТМ."""
    resp = client.post("/api/enhancements/gtm", json={
        "well_name": "Well-101",
        "params": SAMPLE_PARAMS,
        "calculation_result": sample_calc_result,
        "measured_q_liq": 95.0,
        "measured_p_wf": 62.0,
        "skin_factor": 2.5
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "order_number" in data
    assert "gtm_type" in data
    assert "ОПЗ" in data["gtm_type"]
    assert "technical_recipe" in data
    assert "markdown_document" in data
    assert "Well-101" in data["markdown_document"]

