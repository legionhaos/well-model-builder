from backend.app.ai_assistant.parsers import parse_message_parameters, parse_upload


def test_parse_json_message():
    payload = {"ipr": {"p_res": 200}, "vlp": {"p_wh": 10}}
    assert parse_message_parameters('{"ipr":{"p_res":200},"vlp":{"p_wh":10}}') == payload


def test_parse_explicit_russian_units_to_atm():
    parsed = parse_message_parameters("пластовое_давление: 10 МПа\nобводненность: 50%")
    assert parsed["ipr"]["p_res"] == 98.69232667
    assert parsed["ipr"]["wct"] == 50


def test_upload_plain_text_rejects_empty_and_unknown():
    result = parse_upload("well.txt", b"p_wh: 10 atm")
    assert result["extracted_values"]["p_wh"]["value"] == 10
