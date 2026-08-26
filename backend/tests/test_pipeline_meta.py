import unittest

from app.services.llm.providers.openrouter import openrouter_call_meta
from app.services.pipeline_meta import (
    extraction_source_type,
    merge_pipeline_meta,
    persist_pipeline_meta,
    slim_stage_for_storage,
    snapshot_prompts,
)


class ExtractionSourceTypeTests(unittest.TestCase):
    def test_keeps_hubspot_and_voice(self):
        self.assertEqual(extraction_source_type("hubspot_call"), "hubspot_call")
        self.assertEqual(extraction_source_type("voice_memo"), "voice_memo")
        self.assertEqual(extraction_source_type("meeting_transcript"), "meeting_transcript")
        self.assertEqual(extraction_source_type("whatsapp"), "voice_memo")
        self.assertEqual(extraction_source_type(None), "voice_memo")


class PipelineMetaTests(unittest.TestCase):
    def test_merge_appends_stages_and_sums_ms(self):
        existing = {"stages": [{"name": "stt", "ms": 1000}]}
        merged = merge_pipeline_meta(
            existing, [{"name": "extract", "ms": 2500}], provider="openrouter"
        )
        self.assertEqual([s["name"] for s in merged["stages"]], ["stt", "extract"])
        self.assertEqual(merged["total_ms"], 3500)
        self.assertEqual(merged["provider"], "openrouter")

    def test_latest_run_wall_is_total_ms(self):
        first = merge_pipeline_meta(
            {},
            [{"name": "extract", "ms": 4000, "run_id": "a"}],
            run={"run_id": "a", "wall_ms": 4200, "trigger": "extract"},
        )
        second = merge_pipeline_meta(
            first,
            [{"name": "extract", "ms": 3000, "run_id": "b"}],
            run={"run_id": "b", "wall_ms": 800, "trigger": "re_extract"},
        )
        self.assertEqual(second["total_ms"], 800)
        self.assertEqual(second["latest_run_id"], "b")
        self.assertEqual(len(second["runs"]), 2)

    def test_slim_drops_prompt_bodies_keeps_char_counts(self):
        stage = {
            "name": "extract",
            "ms": 1200,
            "model": "google/gemini-3.5-flash-lite",
            "prompts": [
                {"role": "system", "chars": 9000, "content": "x" * 9000},
                {"role": "user", "chars": 400, "content": "transcript here"},
            ],
        }
        slim = slim_stage_for_storage(stage)
        self.assertEqual(slim["model"], "google/gemini-3.5-flash-lite")
        self.assertEqual(slim["prompts"][0]["chars"], 9000)
        self.assertNotIn("content", slim["prompts"][0])
        self.assertNotIn("content", slim["prompts"][1])

    def test_snapshot_prompts_records_char_counts(self):
        snaps = snapshot_prompts([{"role": "user", "content": "hello"}])
        self.assertEqual(snaps, [{"role": "user", "chars": 5, "content": "hello"}])

    def test_pipeline_run_yields_the_same_list_record_stage_appends_to(self):
        import time
        from app.services.pipeline_meta import pipeline_run, record_stage

        started = time.perf_counter()
        with pipeline_run() as stages:
            record_stage("extract", started, model="google/gemini-3.5-flash-lite")
        self.assertEqual(len(stages), 1)
        self.assertEqual(stages[0]["name"], "extract")
        self.assertEqual(stages[0]["model"], "google/gemini-3.5-flash-lite")


class OpenRouterCallMetaTests(unittest.TestCase):
    def test_uses_routed_model_and_completion_tokens(self):
        meta = openrouter_call_meta(
            {
                "model": "google/gemini-3.5-flash-lite",
                "usage": {
                    "prompt_tokens": 1800,
                    "completion_tokens": 220,
                    "total_tokens": 2020,
                },
            },
            requested_model="google/gemini-3.5-flash-lite",
        )
        self.assertEqual(meta["model"], "google/gemini-3.5-flash-lite")
        self.assertEqual(meta["prompt_tokens"], 1800)
        self.assertEqual(meta["completion_tokens"], 220)
        self.assertEqual(meta["total_tokens"], 2020)


class ReExtractLayoutTests(unittest.TestCase):
    def test_hubspot_calls_are_not_skipped(self):
        import ast
        from pathlib import Path

        tree = ast.parse(
            Path(__file__).resolve().parents[1].joinpath("app/api/memos.py").read_text()
        )
        fn = next(
            n for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "re_extract_memo"
        )
        extract_calls = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Attribute) and n.attr == "extract"
        ]
        self.assertTrue(extract_calls, "re_extract_memo must call extraction_service.extract")
        gated = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Compare)
            and any(
                isinstance(c, ast.Tuple)
                and any(
                    isinstance(elt, ast.Constant) and elt.value == "hubspot_call"
                    for elt in c.elts
                )
                for c in n.comparators
            )
        ]
        self.assertEqual(
            gated,
            [],
            "re_extract must not skip hubspot_call / voice_memo behind a source_type gate",
        )


class PersistPipelineMetaTests(unittest.TestCase):
    def test_persist_strips_prompt_bodies_and_records_empty_run(self):
        store = {"memo-1": {"pipeline_meta": {}}}

        class _Result:
            def __init__(self, data):
                self.data = data

        class _Query:
            def __init__(self, store):
                self.store = store
                self._op = None
                self._payload = None
                self._memo_id = None

            def select(self, *_args, **_kwargs):
                self._op = "select"
                return self

            def update(self, payload):
                self._op = "update"
                self._payload = payload
                return self

            def eq(self, key, value):
                if key == "id":
                    self._memo_id = value
                return self

            def limit(self, _n):
                return self

            def execute(self):
                if self._op == "select":
                    return _Result([self.store.get(self._memo_id, {})])
                row = dict(self.store.get(self._memo_id, {}))
                row.update(self._payload or {})
                self.store[self._memo_id] = row
                return _Result([row])

        class _Client:
            def table(self, _name):
                return _Query(store)

        persist_pipeline_meta(
            _Client(),
            "memo-1",
            [
                {
                    "name": "extract",
                    "ms": 1200,
                    "model": "google/gemini-3.5-flash-lite",
                    "prompts": [
                        {"role": "system", "chars": 9000, "content": "x" * 9000},
                    ],
                }
            ],
        )
        meta = store["memo-1"]["pipeline_meta"]
        self.assertEqual(meta["stages"][0]["model"], "google/gemini-3.5-flash-lite")
        self.assertNotIn("content", meta["stages"][0]["prompts"][0])
        self.assertNotIn("empty_run", meta)

        store["memo-empty"] = {}
        persist_pipeline_meta(_Client(), "memo-empty", [])
        empty_meta = store["memo-empty"]["pipeline_meta"]
        self.assertTrue(empty_meta["empty_run"])
        self.assertEqual(empty_meta.get("stages") or [], [])


if __name__ == "__main__":
    unittest.main()

