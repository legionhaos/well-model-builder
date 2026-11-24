# Тестовая скважина well_01

Тестовые данные для самопроверки сервисов IPR, VLP и Nodal.

## IPR

**Запрос** - `requests/ipr.json`:

- `p_res` — пластовое давление, атм;
- `wct` — обводнённость, %;
- `pi` — коэффициент продуктивности, м³/сут/атм;
- `pb` — давление насыщения, атм;
- `points` — число точек, опционально, по умолчанию 21.

**Ответ** - `expected/ipr.json`:

- `q_liq[]` — дебит жидкости, м³/сут;
- `p_wf[]` — забойное давление, атм;

## VLP

**Запрос** - `requests/vlp.json`:

- `inclinometry.MD`, `inclinometry.TVD` — м;
- `casing.d`, `tubing.d`, `tubing.h_mes` — м;
- `pvt.wct` — %; `pvt.rp` — м³/т; `pvt.gamma_oil`, `pvt.gamma_gas`, `pvt.gamma_wat` — безразмерные; `pvt.t_res` — °C;
- `p_wh` — атм;
- `geo_grad`;
- `h_res` — м;
- `roughness`, `q_max`, `points` — опционально.

**Ответ** - `expected/vlp.json`:

- `q_liq[]` — дебит жидкости, м³/сут;
- `p_wf[]` — забойное давление, атм;

## Nodal

**Запрос** - `requests/nodal.json`:

- `ipr.q_liq[]`, `ipr.p_wf[]`;
- `vlp.q_liq[]`, `vlp.p_wf[]`.

Это две кривые - результат работы сервисов IPR, VLP/

**Ответ** - `expected/nodal.json`:

- массив ровно из одной точки;
- `{"q_liq": ..., "p_wf": ...}`;
- единицы совпадают с входными.

## Файлы

- `requests/ipr.json`, `requests/vlp.json`, `requests/nodal.json`;
- `expected/ipr.json`, `expected/vlp.json`, `expected/nodal.json`.

## Как проверять

Проверять можно командами или своим скриптом.

### Командами

1. Поднять сервисы:

   ```bash
   docker compose up -d --build ipr vlp nodal
   ```

2. Отправить запросы из `requests/` через `curl`, Postman или PowerShell.

   Пример для IPR:

   ```bash
   curl -X POST http://localhost:8003/ipr/calc \
     -H "Content-Type: application/json" \
     -d @requests/ipr.json
   ```

3. Сравнить ответы с `expected/`.

### Своим скриптом

Скрипт должен:

- прочитать `requests/*.json`;
- отправить POST на нужный порт;
- проверить HTTP 200 и `Content-Type: application/json`;
- проверить длины массивов и отсутствие `NaN`/`Inf`;
- сравнить с `expected/` с допусками.

Для Nodal можно использовать готовый `requests/nodal.json`.
Для сквозной проверки сначала вызовите IPR и VLP, затем передайте их ответы в Nodal.

## Допуски

- IPR, VLP, Nodal — 5 %;
- E2E — 10 %.

## Важно

- Не использовать тестовые данные для хардкода эталонных ответов.
- Организаторы для проверки используют другие тестовые данные.

