from app.services.hubspot.tasks import TaskBatchResult, TaskSkip, summarize_task_batch


def test_summarize_task_batch_none_when_all_created():
    batch = TaskBatchResult(created_ids=["1", "2"])
    assert summarize_task_batch(2, batch) is None


def test_summarize_task_batch_duplicate_skips():
    batch = TaskBatchResult(
        skipped=[TaskSkip(reason="duplicate", step="Call back", subject="Call back")],
    )
    msg = summarize_task_batch(1, batch)
    assert msg is not None
    assert "No tasks were created" in msg
    assert "duplicate" in msg


def test_summarize_task_batch_merge_no_changes():
    batch = TaskBatchResult()
    msg = summarize_task_batch(2, batch, merge_mode=True)
    assert msg is not None
    assert "No new tasks were added" in msg


def test_summarize_task_batch_merge_failed():
    batch = TaskBatchResult()
    msg = summarize_task_batch(1, batch, merge_failed=True)
    assert msg is not None
    assert "Could not merge tasks" in msg


def test_summarize_task_batch_already_synced():
    batch = TaskBatchResult()
    msg = summarize_task_batch(1, batch, already_synced=True)
    assert msg is not None
    assert "already synced" in msg
