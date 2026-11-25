import asyncio
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.ai_assistant import parsers, storage
from app.enhancements.audio import transcribe_audio_file
from app.enhancements.report import (
    generate_csv_report,
    generate_excel_report,
    generate_html_report,
    generate_json_report,
    generate_markdown_report,
)
from app.enhancements.vision import extract_parameters_from_image
from app.main import app
from app.orchestrator.diagnostics import collect_physics_warnings

client = TestClient(app)


SAMPLE_WELL_PARAMS = {
    "ipr": {"p_res": 200.0, "wct": 50.0, "pi": 1.0, "pb": 150.0, "points": 21},
    "vlp": {
        "inclinometry": {"MD": [0.0, 1000.0, 1500.0], "TVD": [0.0, 1000.0, 1100.0]},
        "casing": {"d": 0.1},
        "tubing": {"d": 0.062, "h_mes": 1000.0},
        "pvt": {
            "wct": 50.0,
            "rp": 100.0,
            "gamma_oil": 0.8,
            "gamma_gas": 0.7,
            "gamma_wat": 1.0,
            "t_res": 90.0,
        },
        "p_wh": 10.0,
        "geo_grad": 0.03,
        "h_res": 1500.0,
    },
}


def test_physics_warnings_detect_negative_flow_and_invalid_wct():
    # Valid case produces no warnings
    clean_res = {"operating_point": {"q_liq": 120.5, "p_wf": 95.0}, "ipr": {"q_liq": [0, 50, 120]}}
    assert collect_physics_warnings(SAMPLE_WELL_PARAMS["ipr"], SAMPLE_WELL_PARAMS["vlp"], clean_res) == []

    # Invalid WCT, p_wh >= p_res, pb > p_res, tubing >= casing, negative q_liq
    bad_ipr = {"p_res": 100.0, "wct": 115.0, "pi": 0.0, "pb": 150.0}
    bad_vlp = {
        "p_wh": 120.0,
        "h_res": 900.0,
        "tubing": {"d": 0.12, "h_mes": 1200.0},
        "casing": {"d": 0.10},
        "pvt": {"wct": 50.0},
    }
    bad_res = {"operating_point": {"q_liq": -15.0, "p_wf": 115.0}, "ipr": {"q_liq": [-10.0, 20.0]}}
    warnings = collect_physics_warnings(bad_ipr, bad_vlp, bad_res)

    joined = " | ".join(warnings)
    assert "WCT = 115.0%" in joined
    assert "P_wh" in joined
    assert "P_b" in joined
    assert "НКТ" in joined
    assert "q_liq = -15.00" in joined
    assert "отрицательные значения дебита" in joined


def test_reports_include_explicit_warnings_without_blocking():
    calc_result = {
        "status": "ok",
        "operating_point": {"q_liq": -5.2, "p_wf": 210.0},
        "warnings": ["Отрицательный расчётный дебит q_liq = -5.20 м³/сут."],
    }
    md = generate_markdown_report("TestWell", SAMPLE_WELL_PARAMS, calc_result)
    assert "ПРЕДУПРЕЖДЕНИЕ — обнаружены аномалии расчёта" in md
    assert "-5.20" in md

    html = generate_html_report("TestWell", SAMPLE_WELL_PARAMS, calc_result)
    assert "ВНИМАНИЕ: обнаружены предупреждения и аномалии расчёта" in html

    csv_text = generate_csv_report("TestWell", SAMPLE_WELL_PARAMS, calc_result)
    assert "ПРЕДУПРЕЖДЕНИЕ" in csv_text

    json_data = generate_json_report("TestWell", SAMPLE_WELL_PARAMS, calc_result)
    assert any("-5.20" in w for w in json_data["warnings"])

    xlsx_bytes = generate_excel_report("TestWell", SAMPLE_WELL_PARAMS, calc_result)
    assert len(xlsx_bytes) > 500


def test_server_storage_save_list_read_and_traversal_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))

    saved = storage.save_uploaded_file(
        "../../weird path/well_doc.txt",
        b"P_res: 215 atm\nWCT: 45 %\n",
        parsed={"text": "P_res: 215 atm", "parsed_params": {"ipr": {"p_res": 215.0}}},
    )
    assert saved["saved_name"] == "well_doc.txt"
    assert (tmp_path / "well_doc.txt").exists()
    assert (tmp_path / "well_doc.txt.meta.json").exists()

    listed = storage.list_server_files()
    assert any(item["name"] == "well_doc.txt" and item["folder"] == "uploads" for item in listed)

    loaded = storage.read_server_file("well_doc.txt", folder="uploads")
    assert loaded["parsed_params"]["ipr"]["p_res"] == 215.0

    try:
        storage.read_server_file("../etc/passwd", folder="uploads")
        raise AssertionError("Expected traversal lookup to fail")
    except FileNotFoundError:
        pass


def test_pdf_image_ocr_fallback(monkeypatch):
    class FakePage:
        def extract_text(self):
            return ""

        images = [SimpleNamespace(name="scan_p1.png", data=b"x" * 2048)]

    class FakeReader:
        def __init__(self, *args, **kwargs):
            self.pages = [FakePage()]

    async def fake_vision(filename, content, llm_override=None):
        assert filename == "scan_p1.png"
        assert llm_override == {"api_key": "k-test"}
        return {
            "available": True,
            "extracted_params": {"ipr": {"p_res": 245.0, "wct": 30.0}, "vlp": {"p_wh": 12.0}},
            "raw_text": "P_res: 245 атм\nWCT: 30%\nP_wh: 12 атм",
        }

    monkeypatch.setattr("pypdf.PdfReader", FakeReader)
    monkeypatch.setattr("app.enhancements.vision.extract_parameters_from_image", fake_vision)

    res = asyncio.run(parsers.parse_upload_with_vision("scan.pdf", b"%PDF-1.4 dummy", llm_override={"api_key": "k-test"}))
    assert res["parsed_params"]["ipr"]["p_res"] == 245.0
    assert res["parsed_params"]["vlp"]["p_wh"] == 12.0
    assert any("Vision: scan_p1.png" in s for s in res["sources"])


def test_vision_and_audio_do_not_return_fake_success_without_llm_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    vis = asyncio.run(extract_parameters_from_image("img.png", b"pngbytes"))
    assert vis["status"] == "unavailable"
    assert vis["extracted_params"] is None

    aud = asyncio.run(transcribe_audio_file("voice.webm", b"webmbytes"))
    assert aud["status"] == "unavailable"
    assert aud["transcript"] == ""


def test_chat_status_override_and_files_endpoints_and_stream(monkeypatch, tmp_path):
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    # Without env keys, status is unavailable; header overrides make chat status available
    base_status = client.get("/api/chat/status")
    assert base_status.status_code == 200
    assert base_status.json()["available"] is False

    res = client.get(
        "/api/chat/status",
        headers={
            "X-LLM-Base-Url": "https://api.example.com/v1",
            "X-LLM-Model": "gpt-4o-mini",
            "X-LLM-Api-Key": "sk-ui-test",
        },
    )
    assert res.status_code == 200
    assert res.json()["available"] is True

    # Upload saves to server and exposes via /api/chat/files
    up = client.post(
        "/api/chat/upload",
        files={"file": ("well_input.txt", "P_res: 210 atm\nWCT: 40 %".encode("utf-8"), "text/plain")},
    )
    assert up.status_code == 200
    body = up.json()
    assert body["filename"] == "well_input.txt"
    assert body["extracted_values"]["p_res"]["value"] == 210.0

    files_res = client.get("/api/chat/files")
    assert files_res.status_code == 200
    assert any(f["name"] == "well_input.txt" for f in files_res.json()["files"])

    read_res = client.get("/api/chat/files/uploads/well_input.txt")
    assert read_res.status_code == 200
    assert read_res.json()["extracted_values"]["p_res"]["value"] == 210.0

    # Streaming endpoint works cleanly in offline mode and returns SSE JSON events
    with client.stream("POST", "/api/chat/stream", json={"message": "привет"}) as stream_res:
        assert stream_res.status_code == 200
        raw_stream = "".join(stream_res.iter_text())
    assert '"type": "status"' in raw_stream
    assert '"type": "done"' in raw_stream


def test_mcp_server_stdio_tools_list_and_call(tmp_path):
    mcp_path = Path(__file__).resolve().parents[3] / "mcp_server.py"
    if not mcp_path.exists():
        mcp_path = Path("/app/mcp_server.py")
    assert mcp_path.exists()

    (tmp_path / "mcp_sample.txt").write_text("P_res: 230 atm\nP_wh: 14 atm\n", encoding="utf-8")
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "UPLOAD_STORAGE_DIR": str(tmp_path)}
    payload = "\n".join(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
            json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "list_server_files", "arguments": {}},
                }
            ),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "read_server_file",
                        "arguments": {"name": "mcp_sample.txt", "folder": "uploads"},
                    },
                }
            ),
        ]
    ) + "\n"

    proc = subprocess.run(
        [sys.executable, str(mcp_path)],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
        check=True,
    )
    responses = [json.loads(line) for line in proc.stdout.strip().splitlines() if line.strip()]
    assert len(responses) == 4
    tool_names = [t["name"] for t in responses[1]["result"]["tools"]]
    assert {"list_server_files", "read_server_file", "calculate_well_model"} <= set(tool_names)

    listed_files = json.loads(responses[2]["result"]["content"][0]["text"])["files"]
    assert any(f["name"] == "mcp_sample.txt" for f in listed_files)

    read_data = json.loads(responses[3]["result"]["content"][0]["text"])
    assert read_data["parsed_params"]["ipr"]["p_res"] == 230.0
