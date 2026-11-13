"""crm_configurations.create_tasks and Pipedrive calls on no deal: what Vocify proposes and writes as tasks."""

from types import SimpleNamespace

from app.models.memo import MemoExtraction
from app.services.commitment_tasks import proposes_tasks, rep_added_only

ON = SimpleNamespace(create_tasks=True)
OFF = SimpleNamespace(create_tasks=False)


def test_tasks_proposed_unless_turned_off_or_pipedrive_without_deal():
    assert proposes_tasks(ON, "hubspot", skip_deal=False)
    assert proposes_tasks(None, "pipedrive", skip_deal=False)
    assert proposes_tasks(ON, "hubspot", skip_deal=True)
    assert not proposes_tasks(OFF, "hubspot", skip_deal=False)
    assert not proposes_tasks(OFF, "pipedrive", skip_deal=False)
    assert not proposes_tasks(ON, "pipedrive", skip_deal=True)


def _extraction(steps, **raw):
    return MemoExtraction(nextSteps=steps, raw_extraction=raw or None)


STORED = {
    "nextSteps": ["Enviar propuesta"],
    "intelligence": {"commitments": [{"id": "c1", "text": "llamar el viernes"}]},
}


def test_unreviewed_writes_no_task():
    assert rep_added_only(_extraction(["Enviar propuesta"]), STORED, reviewed=False).nextSteps == []


def test_reviewed_keeps_only_what_the_rep_wrote_with_its_own_schedule():
    out = rep_added_only(
        _extraction(
            ["Enviar propuesta", "Llamar el viernes", "Mandar el contrato a Marta"],
            nextStepSchedules=["", "el viernes", "mañana"],
            reviewedTaskDates=["", "", "2026-11-20"],
        ),
        STORED,
        reviewed=True,
    )
    assert out.nextSteps == ["Mandar el contrato a Marta"]
    assert out.raw_extraction["nextStepSchedules"] == ["mañana"]
    assert out.raw_extraction["reviewedTaskDates"] == ["2026-11-20"]


def test_nothing_stored_keeps_every_reviewed_row():
    assert rep_added_only(_extraction(["Una tarea"]), None, reviewed=True).nextSteps == ["Una tarea"]
