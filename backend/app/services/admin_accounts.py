from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _memo_company(extraction: Any) -> str:
    if not isinstance(extraction, dict):
        return "Untitled memo"
    company = (extraction.get("companyName") or extraction.get("company_name") or "").strip()
    return company or "Untitled memo"


def assemble_account_list_items(
    profiles: List[dict],
    auth_users: List[dict],
    connections: List[dict],
    memos: List[dict],
) -> List[dict]:
    auth_by_id = {str(u.get("id")): u for u in auth_users if u.get("id")}
    connections_by_user: Dict[str, List[dict]] = {}
    for conn in connections:
        uid = str(conn.get("user_id") or "")
        connections_by_user.setdefault(uid, []).append(conn)

    memo_stats: Dict[str, dict] = {}
    for memo in memos:
        uid = str(memo.get("user_id") or "")
        stats = memo_stats.setdefault(
            uid,
            {
                "memo_count": 0,
                "approved_count": 0,
                "failed_count": 0,
                "last_memo_at": None,
            },
        )
        stats["memo_count"] += 1
        status = memo.get("status") or ""
        if status == "approved":
            stats["approved_count"] += 1
        elif status == "failed":
            stats["failed_count"] += 1
        created = memo.get("created_at")
        if created and (stats["last_memo_at"] is None or created > stats["last_memo_at"]):
            stats["last_memo_at"] = created

    items: List[dict] = []
    for profile in profiles:
        uid = str(profile.get("id") or "")
        auth_user = auth_by_id.get(uid, {})
        stats = memo_stats.get(uid, {})
        crm = [
            {
                "provider": c.get("provider"),
                "status": c.get("status"),
                "token_expires_at": c.get("token_expires_at"),
            }
            for c in connections_by_user.get(uid, [])
        ]
        items.append(
            {
                "id": uid,
                "email": auth_user.get("email") or "",
                "full_name": profile.get("full_name"),
                "company_name": profile.get("company_name"),
                "phone": profile.get("phone"),
                "created_at": profile.get("created_at") or "",
                "last_sign_in_at": auth_user.get("last_sign_in_at"),
                "crm": crm,
                "memo_count": stats.get("memo_count", 0),
                "approved_count": stats.get("approved_count", 0),
                "failed_count": stats.get("failed_count", 0),
                "last_memo_at": stats.get("last_memo_at"),
            }
        )
    return items


def compute_usage_from_memos(rows: List[dict]) -> dict:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(
        days=now.weekday(),
        hours=now.hour,
        minutes=now.minute,
        seconds=now.second,
        microseconds=now.microsecond,
    )
    week_start_naive = week_start.replace(tzinfo=None).isoformat() if week_start.tzinfo else week_start.isoformat()

    total_memos = len(rows)
    approved_count = sum(1 for r in rows if r.get("status") == "approved")
    rejected_count = sum(1 for r in rows if r.get("status") == "rejected")
    this_week_memos = 0
    this_week_approved = 0
    time_saved_sec = 0.0
    this_week_time_sec = 0.0
    day_counts = {i: 0 for i in range(7)}

    for r in rows:
        created = r.get("created_at")
        dur = r.get("audio_duration") or 0
        try:
            dur_f = float(dur)
        except (TypeError, ValueError):
            dur_f = 0.0
        time_saved_sec += dur_f

        if not created:
            continue
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if isinstance(created, str) else created
            if getattr(dt, "tzinfo", None):
                dt = dt.replace(tzinfo=None)
            created_naive = dt.isoformat() if hasattr(dt, "isoformat") else str(created)
            if created_naive >= week_start_naive:
                this_week_memos += 1
                if r.get("status") == "approved":
                    this_week_approved += 1
                this_week_time_sec += dur_f
            days_ago = (now.replace(tzinfo=None) - dt).days if hasattr(dt, "__sub__") else 0
            if 0 <= days_ago < 7:
                day_counts[dt.weekday()] = day_counts.get(dt.weekday(), 0) + 1
        except Exception:
            pass

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly = [{"day": day_names[i], "memos": day_counts.get(i, 0)} for i in range(7)]

    recent = []
    for r in rows[:15]:
        ext = r.get("extraction") or {}
        status = r.get("status") or ""
        recent.append(
            {
                "action": "Synced to CRM" if status == "approved" else "Created memo",
                "company": _memo_company(ext),
                "time": r.get("created_at") or "",
                "type": "sync" if status == "approved" else "memo",
            }
        )

    accuracy_pct = None
    if approved_count + rejected_count > 0:
        accuracy_pct = round(100.0 * approved_count / (approved_count + rejected_count), 1)

    return {
        "total_memos": total_memos,
        "approved_count": approved_count,
        "this_week_memos": this_week_memos,
        "this_week_approved": this_week_approved,
        "time_saved_hours": round(time_saved_sec * 5 / 3600, 1),
        "this_week_time_saved_hours": round(this_week_time_sec * 5 / 3600, 1),
        "accuracy_pct": accuracy_pct,
        "weekly": weekly,
        "recent_activity": recent,
    }


def assemble_account_detail(
    profile: dict,
    auth_user: dict,
    connections: List[dict],
    configurations: List[dict],
    recent_memos: List[dict],
    usage: dict,
) -> dict:
    config_by_connection = {str(c.get("connection_id")): c for c in configurations if c.get("connection_id")}

    connection_rows = []
    for conn in connections:
        conn_id = str(conn.get("id") or "")
        cfg = config_by_connection.get(conn_id) or {}
        connection_rows.append(
            {
                "id": conn_id,
                "provider": conn.get("provider"),
                "status": conn.get("status"),
                "token_expires_at": conn.get("token_expires_at"),
                "last_synced_at": conn.get("last_synced_at"),
                "configuration": {
                    "default_pipeline_name": cfg.get("default_pipeline_name"),
                    "default_stage_name": cfg.get("default_stage_name"),
                    "allowed_deal_fields": cfg.get("allowed_deal_fields") or [],
                    "allowed_contact_fields": cfg.get("allowed_contact_fields") or [],
                    "allowed_company_fields": cfg.get("allowed_company_fields") or [],
                    "allowed_line_item_fields": cfg.get("allowed_line_item_fields") or [],
                    "auto_create_contacts": cfg.get("auto_create_contacts"),
                    "auto_create_companies": cfg.get("auto_create_companies"),
                    "lost_lead_status_value": cfg.get("lost_lead_status_value"),
                    "on_hold_lead_status_value": cfg.get("on_hold_lead_status_value"),
                }
                if cfg
                else None,
            }
        )

    glossary = profile.get("glossary") or []
    glossary_len = len(glossary) if isinstance(glossary, list) else 0

    memo_rows = []
    for memo in recent_memos:
        ext = memo.get("extraction") or {}
        memo_rows.append(
            {
                "id": memo.get("id"),
                "status": memo.get("status"),
                "source": memo.get("source"),
                "created_at": memo.get("created_at"),
                "company": _memo_company(ext),
                "error_message": memo.get("error_message"),
            }
        )

    return {
        "id": str(profile.get("id") or ""),
        "email": auth_user.get("email") or "",
        "full_name": profile.get("full_name"),
        "company_name": profile.get("company_name"),
        "phone": profile.get("phone"),
        "created_at": profile.get("created_at") or "",
        "last_sign_in_at": auth_user.get("last_sign_in_at"),
        "product_context": profile.get("product_context") or "",
        "stt_languages": profile.get("stt_languages") or [],
        "glossary_length": glossary_len,
        "primary_crm_connection_id": profile.get("primary_crm_connection_id"),
        "connections": connection_rows,
        "recent_memos": memo_rows,
        "usage": usage,
    }
