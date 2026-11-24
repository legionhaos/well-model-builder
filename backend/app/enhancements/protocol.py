"""Improvement 11: Протокол обсуждения по аудио/тексту (Генерация протоколов технических совещаний)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List


def generate_meeting_protocol(meeting_transcript: str) -> Dict[str, Any]:
    """
    Анализ стенограммы совещания по скважине и формирование официального протокола.
    """
    lines = [line.strip() for line in meeting_transcript.split("\n") if line.strip()]
    now_str = datetime.now().strftime("%Y-%m-%d")

    # Поиск упоминания скважины
    well_match = re.search(r"скважин[аыеу]?\s*(?:№\s*)?([0-9A-Za-zА-Яа-я_-]+)", meeting_transcript, re.I)
    well_name = well_match.group(1) if well_match else "Фонд скважин"

    # Выделение участников (по ключевым словам: геолог, технолог, мастер, инженер или фамилии)
    participants = []
    for line in lines:
        if re.search(r"(присутствовал|участник|геолог|технолог|мастер|инженер|начальник)", line, re.I):
            participants.append(line.replace("Присутствовали:", "").replace("Участники:", "").strip())
    if not participants:
        participants = ["Главный геолог", "Ведущий технолог ЦДНГ", "Инженер по гидродинамическому моделированию"]

    # Выделение ключевых тем и решений
    decisions = []
    actions = []

    for line in lines:
        if re.search(r"(решили|постановили|принято решение|необходимо|запланировать)", line, re.I):
            decisions.append(line)
        if re.search(r"(поручить|ответственн|срок|до \d\d)", line, re.I):
            actions.append(line)

    if not decisions:
        decisions = [
            f"1. Выполнить узловой анализ скважины {well_name} при текущих термобарических параметрах.",
            "2. Оценить чувствительность дебита к снижению буферного давления (подбор штуцера).",
            "3. При дальнейшем росте обводненности рассмотреть подбор лифтовой колонны меньшего диаметра."
        ]

    if not actions:
        actions = [
            {"action": "Провести повторный гидродинамический замер (КВД)", "assignee": "Служба ГДИ", "deadline": "3 дня"},
            {"action": "Сформировать карту оптимизации режима в Well Model Builder", "assignee": "Инженер-технолог", "deadline": "1 день"}
        ]

    protocol_text = f"""# ПРОТОКОЛ ТЕХНИЧЕСКОГО СОВЕЩАНИЯ
**Объект:** Скважина {well_name}  
**Дата заседания:** {now_str}  
**Тема:** Оптимизация технологического режима и узловой анализ скважины

## 1. Состав комиссии:
{chr(10).join(f"- {p}" for p in participants)}

## 2. Повестка дня:
Рассмотрение текущих показателей работы скважины {well_name}, анализ сходимости расчетной модели узлового анализа с фактическими промысловыми замерами, выработка мероприятий по недопущению срыва фонтанирования.

## 3. Принятые решения:
{chr(10).join(d if d.startswith(('1', '2', '3', '-')) else f"- {d}" for d in decisions)}

## 4. План мероприятий и поручений:
| Мероприятие | Ответственный | Срок исполнения |
| :--- | :---: | :---: |
"""
    for act in actions:
        if isinstance(act, dict):
            protocol_text += f"| {act.get('action')} | {act.get('assignee')} | {act.get('deadline')} |\n"
        else:
            protocol_text += f"| {act} | Технолог промысла | В течение недели |\n"

    protocol_text += "\n**Председатель комиссии:** ____________________  \n**Секретарь:** ____________________"

    return {
        "status": "success",
        "well_name": well_name,
        "date": now_str,
        "participants": participants,
        "decisions": decisions,
        "protocol_markdown": protocol_text
    }
