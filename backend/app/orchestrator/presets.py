from typing import List, Dict, Any

PRESETS: List[Dict[str, Any]] = [
    {
        "id": "well_01",
        "name": "Эталонная скважина well_01 (ТЗ v3.1)",
        "description": "Стандартный тестовый кейс из ТЗ: нефтяная залежь, глубина 1500 м, обводненность 50%",
        "data": {
            "ipr": {
                "p_res": 200.0,
                "wct": 50.0,
                "pi": 1.0,
                "pb": 150.0,
                "points": 21
            },
            "vlp": {
                "inclinometry": {
                    "MD": [0.0, 1000.0, 1500.0],
                    "TVD": [0.0, 1000.0, 1100.0]
                },
                "casing": {"d": 0.1},
                "tubing": {"d": 0.062, "h_mes": 1000.0},
                "pvt": {
                    "wct": 50.0,
                    "rp": 100.0,
                    "gamma_oil": 0.8,
                    "gamma_gas": 0.7,
                    "gamma_wat": 1.0,
                    "t_res": 90.0
                },
                "p_wh": 10.0,
                "geo_grad": 3.0,
                "h_res": 1500.0,
                "roughness": 0.0001,
                "q_max": 400.0,
                "points": 21
            }
        }
    },
    {
        "id": "well_high_wct",
        "name": "Высокообводненная скважина (wct=90%)",
        "description": "Поздняя стадия разработки: высокая плотность столба жидкости и сниженный дебит",
        "data": {
            "ipr": {
                "p_res": 220.0,
                "wct": 90.0,
                "pi": 1.5,
                "pb": 120.0,
                "points": 21
            },
            "vlp": {
                "inclinometry": {
                    "MD": [0.0, 1200.0, 1800.0],
                    "TVD": [0.0, 1200.0, 1600.0]
                },
                "casing": {"d": 0.12},
                "tubing": {"d": 0.073, "h_mes": 1200.0},
                "pvt": {
                    "wct": 90.0,
                    "rp": 40.0,
                    "gamma_oil": 0.85,
                    "gamma_gas": 0.65,
                    "gamma_wat": 1.02,
                    "t_res": 75.0
                },
                "p_wh": 12.0,
                "geo_grad": 2.8,
                "h_res": 1800.0,
                "roughness": 0.0001,
                "q_max": 500.0,
                "points": 21
            }
        }
    },
    {
        "id": "well_no_intersection",
        "name": "Скважина без рабочей точки (не фонтанирует)",
        "description": "Низкое пластовое давление или высокое противодавление на устье: кривая VLP лежит выше IPR",
        "data": {
            "ipr": {
                "p_res": 45.0,
                "wct": 30.0,
                "pi": 0.5,
                "pb": 30.0,
                "points": 21
            },
            "vlp": {
                "inclinometry": {
                    "MD": [0.0, 1000.0, 1500.0],
                    "TVD": [0.0, 1000.0, 1100.0]
                },
                "casing": {"d": 0.1},
                "tubing": {"d": 0.062, "h_mes": 1000.0},
                "pvt": {
                    "wct": 30.0,
                    "rp": 80.0,
                    "gamma_oil": 0.82,
                    "gamma_gas": 0.7,
                    "gamma_wat": 1.0,
                    "t_res": 80.0
                },
                "p_wh": 25.0,
                "geo_grad": 3.0,
                "h_res": 1500.0,
                "roughness": 0.0001,
                "q_max": 300.0,
                "points": 21
            }
        }
    }
]
