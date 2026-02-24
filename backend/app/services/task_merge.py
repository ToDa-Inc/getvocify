"""
Task merge service for updating existing deals.

When a new audio/memo is matched to an existing deal, this service analyzes
the existing tasks and the new extraction to produce add/update/delete operations.
Avoids creating duplicates when the user says "la del miércoles se mantiene"
or "la del martes se mueve al jueves".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from app.models.memo import MemoExtraction
from app.services.llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class TaskAdd:
    """New task to create."""
    subject: str
    due_date: Optional[datetime] = None


@dataclass
class TaskUpdate:
    """Existing task to update."""
    id: str
    subject: Optional[str] = None
    due_date: Optional[datetime] = None


@dataclass
class TaskMergeResult:
    """Result of merging new extraction with existing tasks."""
    add: list[TaskAdd] = field(default_factory=list)
    update: list[TaskUpdate] = field(default_factory=list)
    delete: list[str] = field(default_factory=list)


def _format_task_for_prompt(t: dict) -> str:
    """Format a task dict for the LLM prompt."""
    subj = t.get("subject", "")
    due = t.get("due_date")
    due_str = due.strftime("%Y-%m-%d") if due else "sin fecha"
    return f"- ID {t['id']}: \"{subj}\" (fecha: {due_str})"


def _parse_date_from_llm(value: Optional[str]) -> Optional[datetime]:
    """Parse YYYY-MM-DD from LLM output."""
    if not value or not isinstance(value, str):
        return None
    s = value.strip()[:10]
    if len(s) < 10:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


class TaskMergeService:
    """
    Merges new extraction nextSteps with existing deal tasks.
    Uses LLM to decide: add new, update existing (e.g. move date), delete.
    """

    def __init__(self) -> None:
        self.llm = LLMClient()

    async def merge_tasks(
        self,
        existing_tasks: list[dict],
        extraction: MemoExtraction,
        transcript: Optional[str] = None,
    ) -> TaskMergeResult:
        """
        Analyze existing tasks + new extraction and return add/update/delete operations.

        Args:
            existing_tasks: List of {id, subject, due_date} from HubSpot
            extraction: MemoExtraction with nextSteps from new audio
            transcript: Optional transcript snippet for context

        Returns:
            TaskMergeResult with add, update, delete lists
        """
        if not existing_tasks and not (extraction.nextSteps or []):
            return TaskMergeResult()

        # If no existing tasks, fall back to "add all" (handled by sync)
        if not existing_tasks:
            return TaskMergeResult()

        existing_str = "\n".join(_format_task_for_prompt(t) for t in existing_tasks)
        next_steps_str = "\n".join(f"- {s}" for s in (extraction.nextSteps or []))
        transcript_snippet = ""
        if transcript and len(transcript) > 50:
            transcript_snippet = transcript[:2000] + ("..." if len(transcript) > 2000 else "")

        prompt = f"""Tienes un Deal existente con estas tareas en HubSpot:

{existing_str}

El usuario ha grabado un nuevo audio. De la transcripción se han extraído estos next steps:

{next_steps_str}
"""

        if transcript_snippet:
            prompt += f"""

Fragmento de la transcripción (contexto):
\"\"\"
{transcript_snippet}
\"\"\"
"""

        prompt += """

INSTRUCCIONES CRÍTICAS:
- Si el usuario dice que una tarea "se mueve" o "se pasa" a otro día (ej: "la del martes al jueves"), debes ACTUALIZAR la tarea existente (cambiar fecha), NO crear una nueva.
- Si el usuario dice que una tarea "se mantiene" o "sigue igual" o "se mantiene pendiente", NO hagas nada con esa tarea (ni add, ni update, ni delete).
- Si el usuario dice que una tarea "no se hace" o "se cancela", debes ELIMINAR esa tarea.
- Solo CREA nuevas tareas para next steps que son realmente nuevos y no corresponden a tareas existentes.
- Relaciona por concepto y fecha: "llamada martes" ≈ tarea con "martes" en subject o fecha martes; "seguimiento miércoles" ≈ tarea miércoles.

Devuelve JSON con esta estructura exacta:
{
  "add": [{"subject": "texto", "due_date": "YYYY-MM-DD o null"}],
  "update": [{"id": "task_id", "subject": "nuevo texto o null", "due_date": "YYYY-MM-DD o null"}],
  "delete": ["task_id"]
}

- add: solo tareas NUEVAS que no existen
- update: tareas existentes a modificar (id es obligatorio; subject y due_date opcionales)
- delete: ids de tareas a eliminar (canceladas/no se harán)

Si no hay cambios, devuelve add: [], update: [], delete: [].
Devuelve ÚNICAMENTE JSON válido, sin texto adicional."""

        messages = [
            {
                "role": "system",
                "content": "Eres un asistente que analiza tareas de CRM. Devuelves solo JSON válido.",
            },
            {"role": "user", "content": prompt},
        ]

        try:
            out = await self.llm.chat_json(messages, temperature=0.0)
        except Exception as e:
            logger.warning("Task merge LLM failed: %s. Falling back to add-only.", e)
            return TaskMergeResult()

        add_list = out.get("add") or []
        update_list = out.get("update") or []
        delete_list = out.get("delete") or []

        if not isinstance(add_list, list):
            add_list = []
        if not isinstance(update_list, list):
            update_list = []
        if not isinstance(delete_list, list):
            delete_list = []

        result = TaskMergeResult()

        for a in add_list:
            if isinstance(a, dict) and a.get("subject"):
                due = _parse_date_from_llm(a.get("due_date"))
                result.add.append(TaskAdd(subject=str(a["subject"])[:255], due_date=due))

        for u in update_list:
            if isinstance(u, dict) and u.get("id"):
                tid = str(u["id"])
                subj = u.get("subject") if u.get("subject") else None
                due_val = u.get("due_date")
                due = _parse_date_from_llm(due_val) if due_val else None
                result.update.append(TaskUpdate(id=tid, subject=subj, due_date=due))

        for d in delete_list:
            if d:
                result.delete.append(str(d))

        return result
