"""Memo job claim and publish. The atomic rules live in migration 039."""

CLAIM_MEMO_JOB = "claim_memo_job"
PUBLISH_MEMO_JOB = "publish_memo_job"


def claim_statement(kind: str, lease_seconds: int) -> tuple[str, tuple]:
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    return (f"SELECT * FROM {CLAIM_MEMO_JOB}(%s, %s)", (kind, lease_seconds))


def publish_statement(job_id: str, run_id: str, result_json: str) -> tuple[str, tuple]:
    return (f"SELECT {PUBLISH_MEMO_JOB}(%s, %s, %s::jsonb)", (job_id, run_id, result_json))
