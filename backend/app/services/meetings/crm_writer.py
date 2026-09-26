"""Post one meeting activity to HubSpot or Pipedrive using a connection token."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from app.services.meetings.writes import MeetingWriteError

HUBSPOT_BASE = "https://api.hubapi.com"
DEFAULT_TIMEOUT = 30.0
_VOCIFY_OP_PREFIX = "vocify:meeting:"


def writer_from_connection(
    connection: dict[str, Any],
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    contact_id: str | None = None,
    deal_id: str | None = None,
    person_id: str | None = None,
) -> CrmMeetingActivityWriter | None:
    token = (connection.get("access_token") or "").strip()
    if not token:
        return None
    provider = (connection.get("provider") or "").lower()
    if provider not in {"hubspot", "pipedrive"}:
        return None
    api_domain = None
    if provider == "pipedrive":
        meta = connection.get("metadata") or {}
        api_domain = (meta.get("api_domain") or "").rstrip("/")
        if not api_domain:
            return None
    return CrmMeetingActivityWriter(
        provider=provider,
        access_token=token,
        api_domain=api_domain,
        transport=transport,
        timeout=timeout,
        contact_id=contact_id,
        deal_id=deal_id,
        person_id=person_id,
    )


class CrmMeetingActivityWriter:
    """Sync writer for register_meeting: one POST per operation_key unless reconciled."""

    def __init__(
        self,
        *,
        provider: str,
        access_token: str,
        api_domain: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        contact_id: str | None = None,
        deal_id: str | None = None,
        person_id: str | None = None,
    ) -> None:
        self._provider = provider
        self._access_token = access_token
        self._api_domain = api_domain
        self._contact_id = contact_id
        self._deal_id = deal_id
        self._person_id = person_id
        self._remote: dict[str, str] = {}
        self._client = httpx.Client(transport=transport, timeout=timeout)

    def create(self, operation_key: str, proposal: dict) -> str:
        cached = self._remote.get(operation_key)
        if cached:
            return cached
        try:
            if self._provider == "hubspot":
                remote_id = self._create_hubspot(operation_key, proposal)
            else:
                remote_id = self._create_pipedrive(operation_key, proposal)
        except httpx.TimeoutException as exc:
            raise TimeoutError(str(exc)) from exc
        if not remote_id:
            raise MeetingWriteError("failed")
        self._remote[operation_key] = remote_id
        return remote_id

    def reconcile(self, operation_key: str) -> str | None:
        return self._remote.get(operation_key)

    def change_stage(self, mapping: dict | None) -> bool:
        """Forward only: an open deal in the mapped pipeline, currently at an earlier stage."""
        pipeline_id = str((mapping or {}).get("pipeline_id") or "")
        stage_id = str((mapping or {}).get("stage_id") or "")
        if not pipeline_id or not stage_id or not self._deal_id:
            return False
        try:
            if self._provider == "hubspot":
                return self._move_hubspot(pipeline_id, stage_id)
            return self._move_pipedrive(pipeline_id, stage_id)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False

    def _move_hubspot(self, pipeline_id: str, stage_id: str) -> bool:
        deal_url = f"{HUBSPOT_BASE}/crm/v3/objects/deals/{self._deal_id}"
        deal = self._client.get(deal_url, headers=self._headers(), params={"properties": "pipeline,dealstage"})
        if deal.status_code >= 400:
            return False
        props = deal.json().get("properties") or {}
        if str(props.get("pipeline") or "") != pipeline_id:
            return False
        pipeline = self._client.get(f"{HUBSPOT_BASE}/crm/v3/pipelines/deals/{pipeline_id}", headers=self._headers())
        if pipeline.status_code >= 400:
            return False
        stages = {
            str(stage.get("id")): stage
            for stage in pipeline.json().get("stages") or []
            if isinstance(stage, dict)
        }
        current, target = stages.get(str(props.get("dealstage") or "")), stages.get(stage_id)
        if not current or not target:
            return False
        if any(str((stage.get("metadata") or {}).get("isClosed")).lower() == "true" for stage in (current, target)):
            return False
        if int(current.get("displayOrder", 0)) >= int(target.get("displayOrder", 0)):
            return False
        moved = self._client.patch(deal_url, headers=self._headers(), json={"properties": {"dealstage": stage_id}})
        return moved.status_code < 400

    def _move_pipedrive(self, pipeline_id: str, stage_id: str) -> bool:
        base = (self._api_domain or "").rstrip("/")
        deal_url = f"{base}/api/v2/deals/{self._deal_id}"
        deal = self._client.get(deal_url, headers=self._headers())
        if deal.status_code >= 400:
            return False
        data = deal.json().get("data") or {}
        if data.get("status") != "open" or str(data.get("pipeline_id") or "") != pipeline_id:
            return False
        listed = self._client.get(f"{base}/api/v2/stages", headers=self._headers(), params={"pipeline_id": pipeline_id})
        if listed.status_code >= 400:
            return False
        order = {
            str(stage.get("id")): int(stage.get("order_nr", 0))
            for stage in listed.json().get("data") or []
            if isinstance(stage, dict)
        }
        current, target = order.get(str(data.get("stage_id") or "")), order.get(stage_id)
        if current is None or target is None or current >= target:
            return False
        moved = self._client.patch(deal_url, headers=self._headers(), json={"stage_id": int(stage_id)})
        return moved.status_code < 400

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _map_http_error(self, status: int) -> None:
        if status in {401, 403}:
            raise MeetingWriteError("forbidden")
        raise MeetingWriteError("failed")

    def _create_hubspot(self, operation_key: str, proposal: dict) -> str | None:
        starts_at = proposal.get("starts_at") or ""
        ts_ms = _hubspot_timestamp_ms(starts_at)
        subject = _activity_subject(proposal)
        body = f"{_VOCIFY_OP_PREFIX}{operation_key}"
        payload: dict[str, Any] = {
            "properties": {
                "hs_timestamp": ts_ms,
                "hs_task_subject": subject[:255],
                "hs_task_body": body[:65535],
                "hs_task_status": "NOT_STARTED",
                "hs_task_priority": "MEDIUM",
                "hs_task_type": "MEETING",
            }
        }
        associations = []
        if self._deal_id:
            associations.append(
                {
                    "to": {"id": self._deal_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 216}],
                }
            )
        if self._contact_id:
            associations.append(
                {
                    "to": {"id": self._contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
                }
            )
        if associations:
            payload["associations"] = associations
        url = f"{HUBSPOT_BASE}/crm/v3/objects/tasks"
        response = self._client.post(url, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            self._map_http_error(response.status_code)
        data = response.json()
        rid = data.get("id") if isinstance(data, dict) else None
        return str(rid) if rid is not None else None

    def _create_pipedrive(self, operation_key: str, proposal: dict) -> str | None:
        activity_type = self._pipedrive_task_type()
        if not activity_type:
            raise MeetingWriteError("failed")
        due_date, due_time = _pipedrive_due(proposal.get("starts_at"))
        payload: dict[str, Any] = {
            "subject": _activity_subject(proposal)[:255],
            "type": activity_type,
            "note": f"{_VOCIFY_OP_PREFIX}{operation_key}",
        }
        if due_date:
            payload["due_date"] = due_date
        if due_time:
            payload["due_time"] = due_time
        if self._deal_id:
            payload["deal_id"] = int(self._deal_id)
        if self._person_id or self._contact_id:
            payload["person_id"] = int(self._person_id or self._contact_id)
        base = (self._api_domain or "").rstrip("/")
        url = f"{base}/api/v1/activities"
        response = self._client.post(url, headers=self._headers(), json=payload)
        if response.status_code >= 400:
            self._map_http_error(response.status_code)
        data = response.json()
        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if isinstance(data, dict) and data.get("id") is not None:
            return str(data["id"])
        return None

    def _pipedrive_task_type(self) -> str | None:
        base = (self._api_domain or "").rstrip("/")
        url = f"{base}/api/v1/activityTypes"
        response = self._client.get(url, headers=self._headers())
        if response.status_code >= 400:
            self._map_http_error(response.status_code)
        raw = response.json()
        rows = raw.get("data") if isinstance(raw, dict) else raw
        if not isinstance(rows, list):
            return "task"
        for row in rows:
            if not isinstance(row, dict):
                continue
            key = row.get("key_string")
            if key == "task":
                return key
            if row.get("icon_key") == "task":
                return str(key) if key else "task"
        return "task"


def _activity_subject(proposal: dict) -> str:
    tz = proposal.get("timezone") or "UTC"
    starts = proposal.get("starts_at") or ""
    if starts:
        return f"Reunión acordada ({starts}, {tz})"
    return "Reunión acordada"


def _hubspot_timestamp_ms(starts_at: str) -> str:
    if not starts_at:
        dt = datetime.now(timezone.utc)
    else:
        try:
            dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return str(int(dt.timestamp() * 1000))


def _pipedrive_due(starts_at: Optional[str]) -> tuple[str | None, str | None]:
    if not starts_at:
        return None, None
    try:
        dt = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(timezone.utc)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")
