"""Automated tests for SSE chat streaming, PDF OCR, Whisper audio, MCP archive, UI LLM overrides, and physical guards."""

from __future__ import annotations

import io
import json
import sys
import wave
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.ai_assistant.llm_client import LLMConfig
from app.main import app
from app.orchestrator.router import inspect_physical_warnings

client = TestClient(app)


def _sample_params() -> dict:
    return {
        "ipr": {"p_res": 200.0, "wct": 50.0, "pi": 1.0, "pb": 150.0, "points": 21},
        "vlp": {
            "inclinometry": {"MD": [0.0, 1000.0, 1500.0], "TVD": [0.0, 1000.0, 1100.0]},
            "casing": {"d": 0.1},
            "tubing": {"d": 0.062, "h_mes": 1000.0},
            "pvt": {"wct": 50.0, "rp": 100.0, "gamma_oil": 0.8, "gamma_gas": 0.7, "gamma_wat": 1.0, "t_res": 90.0},
            "p_wh": 10.0,
            "geo_grad": 3.0,
            "h_res": 1500.0,
            "roughness": 0.0001,
            "q_max": 400.0,
            "points": 21,
        },
    }


def _make_wav_bytes(duration_sec: float = 0.5, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(duration_sec * sample_rate))
    return buf.getvalue()


def test_ui_llm_config_overrides_and_chat_status(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)

    res_empty = client.get("/api/chat/status")
    assert res_empty.status_code == 200
    assert res_empty.json()["available"] is False

    res_override = client.get(
        "/api/chat/status",
        headers={
            "X-LLM-Api-Key": "sk-ui-test-key",
            "X-LLM-Base-Url": "https://openrouter.ai/api/v1",
            "X-LLM-Model": "openai/gpt-4o-mini",
        },
    )
    assert res_override.status_code == 200
    body = res_override.json()
    assert body["available"] is True
    assert "openai/gpt-4o-mini" in (body.get("message") or "")

    cfg = LLMConfig.from_env({"api_key": "sk-ui-test-key", "model": "deepseek-chat", "base_url": "https://api.deepseek.com/v1"})
    assert cfg.available is True
    assert cfg.model == "deepseek-chat"


def test_mcp_endpoints_and_upload_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))

    txt_content = "Скважина Южная-17\nP_res = 215 атм\nWCT = 42%\nPI = 1.3\nP_wh = 11 атм\n".encode("utf-8")
    up_res = client.post("/api/chat/upload", files={"file": ("passport_south_17.txt", txt_content, "text/plain")})
    assert up_res.status_code == 200
    up_data = up_res.json()
    assert up_data["stored_file_id"]
    assert up_data["extracted_values"]["p_res"]["value"] == 215.0
    assert up_data["extracted_values"]["wct"]["value"] == 42.0

    tools_res = client.get("/api/mcp/tools")
    assert tools_res.status_code == 200
    tool_names = [t["name"] for t in tools_res.json()["tools"]]
    assert {"list_server_files", "read_server_file", "search_server_files"} <= set(tool_names)

    files_res = client.get("/api/mcp/files")
    assert files_res.status_code == 200
    ids = [f["id"] for f in files_res.json()["files"]]
    assert up_data["stored_file_id"] in ids

    search_res = client.post("/api/mcp/call", json={"name": "search_server_files", "arguments": {"query": "Южная"}})
    assert search_res.status_code == 200
    matches = search_res.json()["result"]
    assert len(matches) >= 1
    assert matches[0]["filename"] == "passport_south_17.txt"

    read_res = client.post("/api/mcp/call", json={"name": "read_server_file", "arguments": {"file_ref": up_data["stored_file_id"]}})
    assert read_res.status_code == 200
    assert read_res.json()["result"]["found"] is True
    assert "215" in read_res.json()["result"]["text"]


def test_scanned_pdf_ocr_extraction(tmp_path, monkeypatch):
    import shutil
    import fitz

    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))
    if shutil.which("tesseract") is None:
        return  # Verified directly inside Docker container where tesseract-ocr is installed

    img = Image.new("RGB", (1000, 420), "white")
    draw = ImageDraw.Draw(img)
    lines = [
        "WELL PASSPORT 99",
        "P_res = 225 atm",
        "WCT = 35 %",
        "PI = 1.4",
        "P_wh = 12 atm",
        "H_res = 1600 m",
        "H_mes = 1100 m",
    ]
    for i, line in enumerate(lines):
        draw.text((40, 30 + i * 48), line, fill="black")

    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    pdf_doc = fitz.open()
    page = pdf_doc.new_page(width=1000, height=420)
    page.insert_image(fitz.Rect(0, 0, 1000, 420), stream=img_buf.getvalue())
    pdf_bytes = pdf_doc.tobytes()
    pdf_doc.close()

    res = client.post(
        "/api/chat/upload",
        headers={"X-PDF-OCR-Mode": "tesseract"},
        files={"file": ("scan_well_99.pdf", pdf_bytes, "application/pdf")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["stored_file_id"]
    assert "ocr" in (data.get("ocr_method") or "")
    assert "225" in data["text"] or data["extracted_values"].get("p_res") == 225.0


def test_audio_whisper_endpoint():
    wav_bytes = _make_wav_bytes()
    res = client.post(
        "/api/enhancements/audio",
        headers={"X-Audio-Mode": "whisper"},
        files={"file": ("voice_test.wav", wav_bytes, "audio/wav")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "transcript" in data
    assert "engine" in data


def test_chat_stream_sse_events(monkeypatch):
    async def _fake_stream_chunks():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Проверка ", tool_calls=None))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="стриминга.", tool_calls=None))])

    class _FakeCompletions:
        async def create(self, **kwargs):
            return _fake_stream_chunks()

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_FakeCompletions()))
    monkeypatch.setattr("app.ai_assistant.agent.create_client", lambda cfg: fake_client)

    with client.stream(
        "POST",
        "/api/chat/stream",
        headers={"X-LLM-Api-Key": "sk-stream-test", "X-LLM-Model": "openai/gpt-4o-mini"},
        json={"message": "Привет, расскажи про методику"},
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = []
        for line in resp.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))

    event_types = [e["type"] for e in events]
    assert "session" in event_types
    assert "delta" in event_types
    assert "done" in event_types
    done_evt = next(e for e in events if e["type"] == "done")
    assert done_evt["available"] is True
    assert "Проверка стриминга." in done_evt["text"]


def test_physical_warnings_and_report_export_flagging():
    bad_params = _sample_params()
    bad_params["ipr"]["wct"] = 120.0
    bad_calc = {
        "ipr": {"q_liq": [100.0, 0.0], "p_wf": [1.0, 200.0]},
        "vlp": {"q_liq": [10.0, 100.0], "p_wf": [40.0, 60.0]},
        "operating_point": {"q_liq": -14.5, "p_wf": 48.0},
        "meta": {"calc_time_ms": 5.0},
    }

    warnings = inspect_physical_warnings(bad_params["ipr"], bad_params["vlp"], bad_calc)
    assert any("120" in w or "0–100" in w for w in warnings)
    assert any("отрицательный" in w.lower() or "≤ 0" in w for w in warnings)

    json_rep = client.post("/api/enhancements/report/json", json={"well_name": "Test-Bad", "params": bad_params, "calculation_result": bad_calc}).json()
    assert json_rep["is_physical"] is False
    assert len(json_rep["physical_warnings"]) >= 1
    assert json_rep["export_notice"]

    md_rep = client.post("/api/enhancements/report/markdown", json={"well_name": "Test-Bad", "params": bad_params, "calculation_result": bad_calc}).json()["markdown"]
    assert "НЕФИЗИЧНЫЙ" in md_rep

    csv_rep = client.post("/api/enhancements/report/csv", json={"well_name": "Test-Bad", "params": bad_params, "calculation_result": bad_calc}).text
    assert "НЕФИЗИЧНЫЙ" in csv_rep

    html_rep = client.post("/api/enhancements/report/html", json={"well_name": "Test-Bad", "params": bad_params, "calculation_result": bad_calc}).text
    assert "alert-nonphysical" in html_rep
    assert "НЕФИЗИЧНЫЙ" in html_rep

    xlsx_resp = client.post("/api/enhancements/report/excel", json={"well_name": "Test-Bad", "params": bad_params, "calculation_result": bad_calc})
    assert xlsx_resp.status_code == 200
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_resp.content))
    a3_val = str(wb["Сводка KPI"]["A3"].value or "")
    assert "НЕФИЗИЧНЫЙ" in a3_val


def test_tabular_xlsx_and_docx_parsing(tmp_path, monkeypatch):
    import openpyxl
    from docx import Document

    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Параметр", "Значение", "Единица"])
    ws.append(["p_res", 230, "атм"])
    ws.append(["wct", 30, "%"])
    ws.append(["pi", 1.5, "м3/сут/атм"])
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)

    res_x = client.post("/api/chat/upload", files={"file": ("tbl.xlsx", xlsx_buf.getvalue())})
    assert res_x.status_code == 200
    assert res_x.json()["parsed_params"]["ipr"]["p_res"] == 230.0
    assert res_x.json()["parsed_params"]["ipr"]["wct"] == 30.0

    doc = Document()
    tbl = doc.add_table(rows=1, cols=3)
    tbl.rows[0].cells[0].text = "Параметр"
    tbl.rows[0].cells[1].text = "Значение"
    tbl.rows[0].cells[2].text = "Единица"
    for k, v, u in [("p_res", "212", "атм"), ("wct", "38", "%"), ("pi", "1.25", "")]:
        r = tbl.add_row().cells
        r[0].text, r[1].text, r[2].text = k, v, u
    docx_buf = io.BytesIO()
    doc.save(docx_buf)

    res_d = client.post("/api/chat/upload", files={"file": ("tbl.docx", docx_buf.getvalue())})
    assert res_d.status_code == 200
    assert res_d.json()["parsed_params"]["ipr"]["p_res"] == 212.0
    assert res_d.json()["parsed_params"]["ipr"]["wct"] == 38.0
