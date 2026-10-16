"""Export real calls from the database (read-only) as eval inputs for the live call assistant.

    cd backend && python -m evals.copilot.export_calls 9f125ca1 5c013cf3 ...        # memo id prefixes
    python -m evals.copilot.export_calls --from-prototype ~/getvocify-desktop/app/island/prototype/call.local.json \\
        --user-email rep@company.com --motion discovery

Writes `calls/<id>.local.json`: {id, user_id, company_id, motion, call_mode, playbook_version_id, turns: [{id, who, text, t}]}.
The folder is gitignored (customer speech). Desktop recordings know who spoke from their audio channels (mic = the rep = S1,
as services/intelligence/call_reading.keep_channel_roles); a memo without that is refused, not guessed. Memos carry no
timestamps: `t` is synthesised from the words (0.33 s per word, 0.26 s between turns), as the island prototype plays a call.
Reads whatever SUPABASE_URL points at: with backend/.env that is production. Nothing is written to the database.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

OUT = Path(__file__).with_name("calls")
MS_PER_WORD, GAP_S = 0.33, 0.26


def timed(turns: list[tuple[str, str]]) -> list[dict]:
    """[(who, text)] -> turns with ids and a clock; consecutive turns of the same side are one turn."""
    merged: list[tuple[str, str]] = []
    for who, text in turns:
        text = " ".join(text.split())
        if not text:
            continue
        if merged and merged[-1][0] == who:
            merged[-1] = (who, f"{merged[-1][1]} {text}")
        else:
            merged.append((who, text))
    out, clock = [], 0.0
    for i, (who, text) in enumerate(merged):
        out.append({"id": f"t{i}", "who": who, "text": text, "t": round(clock, 1)})
        clock += max(0.45, len(text.split()) * MS_PER_WORD) + GAP_S
    return out


def supabase():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def export_memo(sb, prefix: str) -> Path:
    from app.services.intelligence.call_reading import split_turns

    def bound(fill: str) -> str:
        h = prefix.replace("-", "").ljust(32, fill)
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"

    found = sb.table("memos").select(
        "id,user_id,company_id,interaction_kind,sales_motion_key,playbook_version_id,transcript,transcript_stt_meta,created_at"
    ).gte("id", bound("0")).lte("id", bound("f")).execute().data
    if len(found) != 1:
        sys.exit(f"{prefix}: {len(found)} memos match")
    memo = found[0]
    if (memo.get("transcript_stt_meta") or {}).get("speakers") != "channels":
        sys.exit(f"{prefix}: sides are not known from the audio channels; not guessing who the rep is")
    parts = [("you" if t["speaker"] == "S1" else "them", t["text"]) for t in split_turns(memo["transcript"]) if t.get("speaker") in ("S1", "S2")]
    call = {
        "id": memo["id"][:8], "memo_id": memo["id"], "user_id": memo["user_id"], "company_id": memo["company_id"],
        "motion": memo["sales_motion_key"], "call_mode": "meeting" if memo["interaction_kind"] == "meeting" else "softphone",
        "playbook_version_id": memo["playbook_version_id"], "turns": timed(parts),
    }
    path = OUT / f"{call['id']}.local.json"
    path.write_text(json.dumps(call, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def export_prototype(sb, path: str, email: str, motion: str) -> Path:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    user = next((u for u in sb.auth.admin.list_users(per_page=1000) if (u.email or "").lower() == email.lower()), None)
    if user is None:
        sys.exit(f"no user {email}")
    company = sb.table("company_members").select("company_id").eq("user_id", user.id).limit(1).execute().data
    call = {
        "id": "proto", "user_id": user.id, "company_id": company[0]["company_id"] if company else None, "motion": motion,
        "call_mode": "softphone", "playbook_version_id": None,
        "turns": timed([("you" if t["you"] else "them", t["text"]) for t in raw["turns"]]),
    }
    out = OUT / "proto.local.json"
    out.write_text(json.dumps(call, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("memos", nargs="*", help="memo id prefixes")
    parser.add_argument("--from-prototype")
    parser.add_argument("--user-email")
    parser.add_argument("--motion", default="discovery")
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    sb = supabase()
    for prefix in args.memos:
        print("wrote", export_memo(sb, prefix))
    if args.from_prototype:
        if not args.user_email:
            sys.exit("--from-prototype needs --user-email: the rep whose playbook the call runs against")
        print("wrote", export_prototype(sb, args.from_prototype, args.user_email, args.motion))


if __name__ == "__main__":
    main()
