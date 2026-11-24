# Руководство по интеграции фронтенда с бэкендом (Well Model Builder v3.1)

Этот документ предназначен для разработчика фронтенда. Здесь описаны базовый URL, формат запросов/ответов, TypeScript-типы, все 12 дополнительных улучшений и примеры вызовов.

---

## 1. Базовый URL и CORS

- **Адрес бэкенда:** `http://localhost:8080` (в Docker и локально).
- **CORS:** Включен на бэкенде (`allow_origins=["*"]`), заголовки разрешены.
- **Swagger / OpenAPI интерактивная документация:** [http://localhost:8080/docs](http://localhost:8080/docs)
- **OpenAPI JSON схема:** [http://localhost:8080/openapi.json](http://localhost:8080/openapi.json)

---

## 2. Базовый расчет узлового анализа (Nodal Analysis)

### `POST /api/calculate`
Основной эндпоинт расчета кривых IPR, VLP и точки пересечения.

#### Входные данные (Request Body JSON):
```json
{
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
    "casing": { "d": 0.1 },
    "tubing": { "d": 0.062, "h_mes": 1000.0 },
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
```

#### Ответ при успехе (HTTP 200 JSON):
```json
{
  "status": "success",
  "ipr": {
    "q_liq": [139.98, 137.93, "...", 0.0],
    "p_wf": [1.0, 10.95, "...", 200.0]
  },
  "vlp": {
    "q_liq": [0.0, 20.0, "...", 400.0],
    "p_wf": [48.19, 48.27, "...", 62.66]
  },
  "operating_point": {
    "q_liq": 127.78,
    "p_wf": 50.27
  },
  "meta": {
    "calc_time_ms": 32.5,
    "message": "Расчет узлового анализа успешно выполнен"
  }
}
```

#### Ответ при срыве потока / отсутствии точки пересечения (HTTP 422 JSON):
Бэкенд **никогда не возвращает 500** и не возвращает фиктивные числа:
```json
{
  "status": "no_intersection",
  "ipr": { "q_liq": [...], "p_wf": [...] },
  "vlp": { "q_liq": [...], "p_wf": [...] },
  "operating_point": null,
  "meta": {
    "calc_time_ms": 28.1,
    "message": "Кривые IPR и VLP не пересекаются в заданном диапазоне расходов. Скважина не способна фонтанировать."
  }
}
```
*На фронтенде: отображайте обе кривые на графике, но скрывайте точку или показывайте бейдж «Срыв фонтанирования».*

---

## 3. Пресеты скважин

### `GET /api/presets`
Возвращает список готовых скважин для кнопок быстрого переключения:
- `well_01`: Эталонная скважина из ТЗ ($q_{liq} = 127.78\text{ м}^3/\text{сут}$, $P_{wf} = 50.27\text{ атм}$).
- `well_high_wct`: Высокая обводненность ($WCT = 85\%$).
- `well_no_intersection`: Случай срыва фонтанирования ($P_{wh} = 70\text{ атм}$).

### `GET /api/presets/{preset_id}`
Возвращает данные конкретного пресета для подстановки в форму.

---

## 4. ИИ-ассистент (Роль 3)

### `GET /api/chat/status`
Проверка готовности ИИ-ассистента:
```json
{
  "available": true,
  "model": "deepseek-v4.1-flash",
  "message": null
}
```

### `POST /api/chat`
Инженерный диалог с Tool Calling и Zero Hallucination:
```json
{
  "message": "Что если снизить буферное давление до 5 атм?",
  "params": { ...текущие_параметры_скважины... },
  "session_id": "optional-uuid"
}
```
Ответ:
```json
{
  "available": true,
  "text": "## Результат сценария «Что если?»...",
  "session_id": "c707be30-...",
  "tool_trace": [
    {
      "step": 1,
      "tool": "run_what_if_scenario",
      "args": { "overrides": { "p_wh": 5.0 } },
      "status": "ok",
      "duration_ms": 128.4
    }
  ],
  "calculation_result": { ...полная_новая_модель_для_графика... }
}
```

### `POST /api/chat/upload`
Загрузка файла (`multipart/form-data`, поле `file`).
Поддерживаемые форматы: `.txt`, `.csv`, `.json`, `.xlsx`, `.docx`, `.pdf`.
Возвращает извлеченные параметры с указанием источника (`sources`).

---

## 5. Все 12 улучшений из презентации (Эндпоинты `/api/enhancements/`)

### 01. Сценарии «Что если»
Работает через обычный запрос в чат (`POST /api/chat`), например:
- *«Что если снизить буферное давление до 5 атм?»*
- *«Что если обводненность вырастет до 70%?»*
Ассистент автоматически вызывает инструмент `run_what_if_scenario`, рассчитывает дельты $\Delta q_{liq}, \Delta p_{wf}$ и возвращает обновленный график.

---

### 02. Распознавание фото и сканов
`POST /api/enhancements/vision`
- Формат: `multipart/form-data`, файл изображения (поле `file`: `.png`, `.jpg`, `.jpeg`).
- Ответ:
```json
{
  "status": "success",
  "filename": "passport_scan.png",
  "method": "multimodal_llm_vision",
  "extracted_params": {
    "ipr": { "p_res": 200, "wct": 50, "pi": 1.0, "pb": 150 },
    "vlp": { "p_wh": 10, "h_res": 1500, "tubing": { "d": 0.062, "h_mes": 1000 } }
  }
}
```

---

### 03. Голосовой ввод
`POST /api/enhancements/audio`
- Формат: `multipart/form-data`, аудиозапись (поле `file`: `.wav`, `.mp3`, `.webm`, `.ogg`).
- Ответ:
```json
{
  "status": "success",
  "filename": "voice.wav",
  "transcript": "Рассчитай рабочую точку скважины при пластовом давлении 200 атм...",
  "extracted_parameters": { "ipr": { "p_res": 200 } }
}
```
*Совет фронтендеру: в браузере Chrome также можно использовать встроенный Web Speech API (`webkitSpeechRecognition`), отправляя распознанный текст прямо в `POST /api/chat`.*

---

### 04. Чтение файлов разных форматов
Работает через `POST /api/chat/upload` (парсит `.txt`, `.csv`, `.json`, `.xlsx`, `.docx`, `.pdf` до 10 МБ).

---

### 05. Экспорт отчетов во всех форматах (HTML, Excel, CSV, JSON, Markdown)
Все методы принимают одинаковое тело запроса:
```json
{
  "well_name": "Скважина 101",
  "params": { ...параметры_скважины... },
  "calculation_result": { ...ответ_расчета... }
}
```

#### 1. Интерактивный HTML-паспорт с графиком:
`POST /api/enhancements/report/html`
- Возвращает красивый автономный одностраничный HTML-документ (не требует внешних CDN, открывается оффлайн на любом устройстве).
- **Включает:**
  - Карточки KPI: $Q_{liq}$ (дебит жидкости), $Q_{oil}$ (чистая нефть), $Q_{gas}$ (попутный газ), $P_{wf}$ (забойное давление), $\Delta P$ (депрессия на пласт) и бейдж статуса фонтанирования.
  - Встроенный чистый векторный SVG-график кривых IPR и VLP с точкой пересечения.
  - Технологические параметры пласта и конструкции скважины.
  - Инженерный аудит и рекомендации технологу.
  - Адаптивные стили `@media print` и встроенную кнопку «Печать / Сохранить в PDF».
- *Вызов в TypeScript:*
  ```typescript
  await api.downloadReportHtml('Скважина 101', params, result);
  ```

#### 2. Microsoft Excel (.xlsx):
`POST /api/enhancements/report/excel`
- Возвращает `.xlsx` с двумя стилизованными вкладками («Сводка KPI» и «Кривые IPR и VLP»).
- *Вызов в TypeScript:*
  ```typescript
  await api.downloadReportExcel('Скважина 101', params, result);
  ```

#### 3. Табличный CSV (.csv):
`POST /api/enhancements/report/csv`
- Возвращает файл CSV с разделителем `;` для открытия в Excel или импорта в симуляторы.
- *Вызов в TypeScript:*
  ```typescript
  await api.downloadReportCsv('Скважина 101', params, result);
  ```

#### 4. Структурированный JSON:
`POST /api/enhancements/report/json`
- Возвращает JSON с рассчитанными KPI (`q_liq_m3_day`, `q_oil_m3_day`, `q_gas_th_m3_day`, `p_wf_atm`, `drawdown_atm`, `flow_regime`), исходными параметрами и кривыми для интеграции с DWH/SCADA.
- *Вызов в TypeScript:*
  ```typescript
  const reportData = await api.getReportJson('Скважина 101', params, result);
  ```

#### 5. Инженерный Markdown:
`POST /api/enhancements/report/markdown`
- Возвращает `{ "well_name": "...", "markdown": "# ИНЖЕНЕРНЫЙ ОТЧЕТ..." }` для Confluence/GitHub вики.


---

### 06. Поиск файлов в папке на сервере
`POST /api/enhancements/scan`
Request Body:
```json
{
  "folder_path": "samples",
  "recursive": true
}
```
Ответ:
```json
{
  "status": "success",
  "scanned_directory": "/app/samples",
  "total_files_found": 3,
  "ready_for_calculation": 1,
  "wells": [
    {
      "filename": "well_01_standard.json",
      "well_name": "Well 01 Standard",
      "format": ".json",
      "is_ready_for_calc": true,
      "validation_status": "Готов к расчету",
      "extracted_parameters": { ... }
    }
  ]
}
```

---

### 07. Защита от вредоносных инструкций
Автоматически активна во всех запросах к `POST /api/chat`. При попытке prompt injection модель мгновенно возвращает отказ без траты токенов.

---

### 08. База знаний RAG по методике со ссылками
Локальная база знаний хранится в `docs/kb/` (Brown 1984, Standing PVT, Colebrook-White). Доступна через чат ассистента или инструмент `search_methodology_kb`.

---

### 09. Подбор параметров режима (Оптимизация)
`POST /api/enhancements/optimize`
Request Body:
```json
{
  "params": { ...параметры_скважины... },
  "optimization_type": "all" // "all" | "tubing" | "wellhead" | "wct"
}
```
Ответ:
```json
{
  "status": "success",
  "results": {
    "tubing_optimization": {
      "best_tubing": { "name": "НКТ 73 мм (базовый)", "d_m": 0.062, "operating_point": { "q_liq": 127.78, "p_wf": 50.27 } },
      "recommendation": "Рекомендуется использовать типоразмер НКТ 73 мм (d = 0.062 м)...",
      "scenarios": [
        { "tubing_name": "НКТ 48 мм", "d_m": 0.0403, "status": "success", "operating_point": { "q_liq": 95.4, "p_wf": 65.1 } },
        { "tubing_name": "НКТ 73 мм (базовый)", "d_m": 0.062, "status": "success", "operating_point": { "q_liq": 127.78, "p_wf": 50.27 } }
      ]
    },
    "critical_wct": {
      "current_wct": 50.0,
      "critical_wct": 90.0,
      "summary": "Критическая обводненность скважины составляет WCT_crit ≈ 90.0%..."
    },
    "wellhead_sensitivity": {
      "optimal_p_wh": 2.0,
      "max_flow_rate": 138.2,
      "recommendation": "Снижение устьевого давления до 2.0 атм позволяет достичь максимального дебита 138.2 м³/сут."
    }
  }
}
```

---

### 10. Сравнение с фактическим замером (History Matching)
`POST /api/enhancements/match`
Request Body:
```json
{
  "params": { ... },
  "measured_q_liq": 115.0,
  "measured_p_wf": 55.0
}
```
Ответ:
```json
{
  "status": "success",
  "comparison": {
    "measured": { "q_liq": 115.0, "p_wf": 55.0 },
    "model": { "q_liq": 127.78, "p_wf": 50.27 },
    "deltas": {
      "delta_q_liq_m3_day": -12.78,
      "delta_q_liq_percent": -10.0,
      "delta_p_wf_atm": 4.73,
      "delta_p_wf_percent": 9.41
    }
  },
  "diagnosis": [
    "Фактический дебит ниже расчетного на 12.78 м³/сут (10.0%). Возможные причины: кольматация призабойной зоны (положительный скин-фактор S > 0)..."
  ],
  "recommendations": [
    "Рекомендуется запланировать гидродинамические исследования (КВД) для определения скин-фактора."
  ],
  "calibrated_parameters": {
    "base_pi": 1.0,
    "recommended_pi": 0.793,
    "formula": "J_calibrated = q_meas / (p_res - p_wf_meas)"
  }
}
```

---

### 11. Протокол совещания
`POST /api/enhancements/protocol`
Request Body:
```json
{
  "transcript": "Совещание по скважине № 102. Присутствовали главный геолог Иванов, технолог Петров. Решили провести промывку НКТ и сменить штуцер. Ответственный мастер участка, срок до 28 ноября."
}
```
Ответ:
```json
{
  "status": "success",
  "well_name": "102",
  "date": "2026-11-24",
  "participants": ["главный геолог Иванов, технолог Петров"],
  "decisions": ["провести промывку НКТ и сменить штуцер"],
  "protocol_markdown": "# ПРОТОКОЛ ТЕХНИЧЕСКОГО СОВЕЩАНИЯ..."
}
```

---

### 12. Пакетный расчет фонда скважин
#### Расчет:
`POST /api/enhancements/batch`
Request Body:
```json
{
  "wells": [
    { "id": "well_101", "name": "Скважина 101", "params": { ... } },
    { "id": "well_102", "name": "Скважина 102", "params": { ... } }
  ]
}
```
Ответ:
```json
{
  "status": "success",
  "summary": {
    "total_wells": 2,
    "flowing_wells": 2,
    "killed_wells": 0,
    "total_q_liq_m3_day": 245.5,
    "total_q_oil_m3_day": 135.2,
    "average_flowing_p_wf_atm": 51.4
  },
  "wells_data": [
    {
      "id": "well_101",
      "name": "Скважина 101",
      "status": "flowing",
      "q_liq_m3_day": 127.78,
      "q_oil_m3_day": 63.89,
      "p_wf_atm": 50.27,
      "wct_pct": 50.0
    }
  ]
}
```

#### Экспорт сводки в Excel:
`POST /api/enhancements/batch/excel` с тем же телом `{ "wells": [...] }` возвращает готовый `.xlsx` файл фонда.

---

## 6. Готовый клиент в TypeScript

В репозитории уже есть готовый клиент со всеми типами:
[frontend/src/api/client.ts](file:///home/scoof/Downloads/well-model-builder/frontend/src/api/client.ts) и [frontend/src/types/well.ts](file:///home/scoof/Downloads/well-model-builder/frontend/src/types/well.ts).

Фронтендер может просто импортировать `api`:
```typescript
import { api } from './api/client';

// 1. Расчет
const result = await api.calculate(params);

// 2. Оптимизация
const opt = await api.optimize(params, 'all');

// 3. Сравнение с фактом
const match = await api.matchMeasurement(params, 115.0, 55.0);

// 4. Скачать Excel отчет
await api.downloadReportExcel('Скважина 101', params, result);
```
