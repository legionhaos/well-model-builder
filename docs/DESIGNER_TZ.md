# ТЗ для дизайнера (UI/UX доработка 5 новых модулей)

Ниже перечислены **5 новых функциональных блоков**, добавленных на фронтенд ([App.tsx](../frontend/src/App.tsx), [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx), [AiChatPanel.tsx](../frontend/src/components/AiChatPanel.tsx), [WellInputForm.tsx](../frontend/src/components/WellInputForm.tsx), [OperatingPointCards.tsx](../frontend/src/components/OperatingPointCards.tsx), [NodalChart.tsx](../frontend/src/components/NodalChart.tsx)). Сейчас они работают на базовых/временных классах и инлайновых отступах, поэтому их нужно оформить в единой дизайн-системе проекта (`styles.css` / `enhancements-ui.css`).

---

## 1. Блок быстрого импорта файла, папки и архива на главной странице
- **Где находится:** [App.tsx](../frontend/src/App.tsx#L583-L680) (сверху над `<WellInputForm>`).
- **Что сейчас есть:**
  - Drag&Drop контейнер с временным инлайновым `style={{ border: '1px dashed ...', background: ... }}` и состоянием перетаскивания `importDragActive`.
  - Заголовок `Импорт файла или папки`, строка статуса `importStatus` (сейчас обрезается `ellipsis` в одну строку).
  - Кнопки **«Папка»** (сейчас временно использует класс `.preset-chip`, из-за чего выглядит как чип пресета) и **«Загрузить файл»** (`.btn-quick-calc`).
  - Список чипов мультискважин при загрузке `.zip` или папки (`importedWells.length > 1`).
- **Что нужно от дизайнера:**
  - Вынести инлайновые стили в отдельный класс (например `.main-import-dropzone` и `.is-dragover`), проработать аккуратное активное состояние при наведении файла (`dragover`).
  - Развести стили кнопки **«Папка»** и чипов пресетов (отдельный класс вторичной кнопки рядом с `.btn-quick-calc`).
  - Оформить состояние ошибки импорта vs успеха и выровнять сетку переключения загруженных скважин (`importedWells`) с выделением активной скважины.

---

## 2. Экран «⚙ Настройки ИИ и API» + пункт в боковом меню + MCP-архив
- **Где находится:**
  - Левый сайдбар `.side-rail` в [App.tsx](../frontend/src/App.tsx#L565-L572) — добавлена кнопка **`⚙ Настройки`** (`openTool('settings')`).
  - Модальное окно/вкладка `active === 'settings'` в [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx#L797-L1028).
- **Что сейчас есть:**
  - Пять кнопок быстрых провайдеров (`.scenarios-chips` -> `.scenario-chip`): OpenRouter, DeepSeek, OpenAI, Ollama.
  - Поля `API Base URL`, `Модель (LLM / Vision)`, `API Key` + кнопка «Показать/Скрыть» с временным `style={{ display: 'flex', gap: '6px' }}`.
  - Два выпадающих списка `<select>` (`Распознавание речи` и `Чтение PDF-сканов`) с временными инлайн-стилями.
  - Блок действий `.tool-actions` (`Сохранить в Cookie (30 дней)`, `Проверить подключение`, `Сбросить`).
  - Блок «Архив файлов на сервере и MCP» (`.tool-results` -> `.scanned-files-list` -> `.scanned-file-item`).
- **Что нужно от дизайнера:**
  - Единый стиль `<select>` под общую типографику инпутов `.tool-fields input` (кастомная стрелка, фокус, отступы).
  - Красивая компоновка строки `API Key + кнопка Показать/Скрыть`, стилизация чипов пресетов (выделение выбранного пресета).
  - Компактная вёрстка карточек файлов серверного архива (`.scanned-file-item`: бейдж источника `uploads` / `samples`, размер, метод OCR `tesseract_ocr` / `vision_ocr`, иконка статуса извлечённых параметров).
  - Проверить активные состояния `.rail-link.active` в левой панели для всех 5 пунктов меню (Главная, Инструменты, База методик, Отчёты, Настройки).

---

## 3. Потоковый SSE-стриминг и трассировка инструментов в чате
- **Где находится:** [AiChatPanel.tsx](../frontend/src/components/AiChatPanel.tsx#L549-L633).
- **Что сейчас есть:**
  - Живая строка статуса перед или внутри ответа ассистента `message.liveStatus` (`Подключение к ИИ-модели...`, `Инструмент: calculate_well_model...`, `Анализ результатов...`) — сейчас переиспользует `.typing`.
  - Потоковое появление Markdown-блоков внутри `.message.assistant .message-text`.
  - Кнопка применения параметров в чате (`.chat-apply-btn` / `.is-applied`) и раскрывающийся список `.tool-trace` (с бейджами `running`, `ok`, `error` и длительностью в `мс`).
  - Иконки прикрепления файлов (`.pdf`, `.zip`, фото, аудио) и кнопка голосового ввода `.voice-button.listening`.
- **Что нужно от дизайнера:**
  - Оформить отдельный аккуратный плавный статус-бар генерации/вызова инструмента (`liveStatus` + статус `running` внутри `.tool-trace`), чтобы он визуально отличался от обычной заглушки набора текста.
  - Подобрать аккуратное отображение таблиц и блоков кода (`<MarkdownView>`) при потоковой дозагрузке текста внутри узкого/расширенного окна `.chat-floating-widget` без скачков скролла.

---

## 4. Предупреждения физической валидации и блокировка отрицательного дебита / WCT
- **Где находится:**
  - Баннер ошибок в форме ввода: [WellInputForm.tsx](../frontend/src/components/WellInputForm.tsx#L137-L148) (`alert alert-warning`).
  - Карточки KPI: [OperatingPointCards.tsx](../frontend/src/components/OperatingPointCards.tsx#L41-L133) (красный блок `.alert.alert-error` при нефизичности/отрицательном дебите, значения KPI `'—'`, текст `Заблокировано (нефизично)`, статус-бейдж `Отклонено` `.status-warning`).
  - График IPR/VLP: [NodalChart.tsx](../frontend/src/components/NodalChart.tsx#L17-L56) (экран `.chart-empty` при блокировке + баннер `.alert.alert-warning` поверх старого валидного графика при неудачном пересчёте).
  - Предупреждение во вкладке экспорта: [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx#L509-L520) (`Экспорт с предупреждением о нефизичности`).
- **Что сейчас есть:**
  - Используются базовые классы `.alert-warning` / `.alert-error` и инлайн `marginBottom: '12px'` / `'10px'`, статус заблокированных KPI использует жёлтый `.status-warning` вместо отдельного критического акцента.
- **Что нужно от дизайнера:**
  - Визуально усилить состояние «Расчёт заблокирован (нефизичный режим / отрицательный дебит)»: чёткий критический бейдж (`status-danger` / красный контур карточек при блокировке), аккуратная вёрстка многострочного списка ошибок внутри `.alert-content` (сейчас `<p>` идут вплотную без маркеров), красивая карточка-заглушка графика в `.chart-empty` при блокировке.

---

## 5. Доработки вкладки «Импорт файлов», «База методик (RAG)» и карточек экспорта
- **Где находится:**
  - Вкладка `active === 'import'`: [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx#L649-L710) — добавлена строка метаданных (`ocr_method`, `stored_file_id`) и кнопка применения параметров в модель (`.btn-apply-param`).
  - Вкладка `active === 'rag'`: [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx#L747-L753) — текст ответа переведён с plain-text на `<MarkdownView content={ragResponse} />` внутри `.rag-answer-text`.
  - Вкладка `active === 'report'`: [EnhancementWorkbench.tsx](../frontend/src/components/EnhancementWorkbench.tsx#L525-L595) — поправлены бейджи `.rep-icon` (`HTML`, `XLSX`, `CSV`, `MD`, `JSON`).
- **Что нужно от дизайнера:**
  - Проверить стили `.rag-answer-text .markdown-rendered-view` (в [styles.css](../frontend/src/styles.css) у `.rag-answer-text` задан `white-space: pre-wrap`, из-за чего внутри HTML-блоков Markdown могут появляться лишние вертикальные отступы — лучше заменить на `white-space: normal` для `.rag-answer-text:has(.markdown-rendered-view)`).
  - Привести кнопку `.btn-apply-param` во вкладках «Импорт» и «Оптимизация» к единому стилю основной/акцентной кнопки действия.
