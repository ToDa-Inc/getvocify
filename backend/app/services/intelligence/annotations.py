"""Human notes. The same annotation id is one note. The author comes from the server."""

from __future__ import annotations


class AnnotationError(Exception):
    def __init__(self, code: str, note: dict | None = None):
        self.code = code
        self.note = note


def accept_annotation(
    store: dict,
    *,
    annotation_id: str,
    client_capture_id: str | None,
    text: str,
    offset_ms: int,
    expected_revision: int | None,
    author_id: str,
    company_id: str,
    memo_id: str | None = None,
) -> dict:
    if offset_ms < 0 or not text.strip():
        raise AnnotationError("invalid")
    key = (author_id, annotation_id)
    existing = store.get(key)
    if existing is None:
        note = {
            "annotation_id": annotation_id,
            "client_capture_id": client_capture_id,
            "memo_id": memo_id,
            "text": text,
            "offset_ms": offset_ms,
            "revision": 1,
            "author_id": author_id,
            "company_id": company_id,
            "source_type": "human_note",
            "replayed": False,
        }
        store[key] = note
        return note
    if memo_id and not existing.get("memo_id"):
        existing["memo_id"] = memo_id
    if existing["text"] == text:
        return {**existing, "replayed": True}
    if expected_revision != existing["revision"]:
        raise AnnotationError("conflict", existing)
    existing["text"] = text
    existing["revision"] = existing["revision"] + 1
    return {**existing, "replayed": False}


def bind_capture(store: dict, *, client_capture_id: str, memo_id: str, author_id: str) -> list[dict]:
    """Attach the reserved memo once. A second bind does not copy the note."""
    bound = []
    for (owner, _annotation_id), note in store.items():
        if owner != author_id or note.get("client_capture_id") != client_capture_id:
            continue
        if note.get("memo_id") and note["memo_id"] != memo_id:
            continue
        note["memo_id"] = memo_id
        bound.append(note)
    return bound


def revise_statement(*, author_id: str, annotation_id: str, text: str, expected_revision: int) -> str:
    safe_text = text.replace("'", "''")
    safe_id = annotation_id.replace("'", "''")
    return (
        "UPDATE interaction_annotations SET text = "
        f"'{safe_text}', revision = revision + 1, updated_at = now() "
        f"WHERE author_id = '{author_id}' AND annotation_id = '{safe_id}' "
        f"AND revision = {int(expected_revision)};"
    )
