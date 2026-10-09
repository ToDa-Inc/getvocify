"""Step-1 CRM extraction in the C04 v8 pipeline: the call was read first."""

import asyncio
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")

from app.services.extraction import ExtractionService

SPECS = [
    {"name": "pains", "object_type": "companies", "type": "enumeration", "label": "Pains",
     "options": [{"value": "leads", "label": "Pocos leads"}]},
]
READING = {"call_type": "cold_first_contact", "phase_reached": "discovery", "roles_marked": True}


class FakeLLM:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    async def chat_json(self, messages, **kwargs):
        self.calls.append(messages)
        return dict(self.reply)


class FakeJev:
    is_available = True

    def __init__(self):
        self.calls = 0

    async def classify_enums(self, *args, **kwargs):
        self.calls += 1
        return {"pains": "leads"}


def _service(reply):
    service = ExtractionService.__new__(ExtractionService)
    service.llm = FakeLLM(reply)
    service.jev = FakeJev()
    return service


def test_no_conversation_writes_one_line_and_calls_no_model():
    service = _service({"summary": "x"})
    out = asyncio.run(service.extract(
        "You: hola\n\nThem: ...", SPECS,
        call_reading={"call_type": "no_conversation", "call_type_reason": "Saltó el buzón."},
    ))
    assert out.summary.startswith("**Resultado:** Sin conversación.")
    assert service.llm.calls == [] and service.jev.calls == 0


def test_grounded_prompt_judges_on_the_prospects_words_and_skips_the_enum_second_passes():
    service = _service({"summary": "**Resultado:** Aceptó una demo.", "nextSteps": []})
    asyncio.run(service.extract(
        "You: soy Ana de Acme\n\nThem: se nos escapan los leads", SPECS, call_reading=READING,
    ))
    system, user = service.llm.calls[0][0]["content"], service.llm.calls[0][1]["content"]
    assert "never facts about the prospect" in system
    assert "Only what the prospect said" in user and "primera conversación" in user
    assert "partner_channel" not in user and "MUST set it" not in user
    assert service.jev.calls == 0 and len(service.llm.calls) == 1  # no Jev, no leftover-enum pass


def test_without_a_reading_the_legacy_prompt_is_unchanged():
    service = _service({"summary": "x"})
    service.jev.is_available = False
    asyncio.run(service.extract("S1: hola\n\nS2: dime", SPECS))
    assert "prefer the best-matching option over null" in service.llm.calls[0][1]["content"]


def test_grounded_cleanup_drops_role_tokens_and_empty_schedules():
    from app.services.extraction import grounded_cleanup
    out = grounded_cleanup({
        "contactName": "Them", "decisionMakers": ["Them", "Pablo"], "nextStepSchedules": ["", ""],
        "contact_properties": {"firstname": "You", "email": "a@b.es"},
    })
    assert out["contactName"] is None and out["decisionMakers"] == ["Pablo"]
    assert out["nextStepSchedules"] == [] and out["contact_properties"] == {"firstname": None, "email": "a@b.es"}
    kept = grounded_cleanup({"nextStepSchedules": ["2026-10-02", ""]})
    assert kept["nextStepSchedules"] == ["2026-10-02", ""]  # parallel to nextSteps


def test_grounded_cleanup_drops_placeholders_and_garbled_identity():
    from app.services.extraction import grounded_cleanup
    out = grounded_cleanup({
        "contactEmail": "abantio.comsiesoes.me",
        "company_properties": {"crm": "CRM Desconocido", "domain": "ltk grupo", "name": "Acme"},
        "contact_properties": {"email": "ana@acme.es"},
    })
    assert out["contactEmail"] is None
    assert out["company_properties"] == {"crm": None, "domain": None, "name": "Acme"}
    assert out["contact_properties"] == {"email": "ana@acme.es"}


def test_a_long_transcript_read_as_no_conversation_still_gets_a_note():
    service = _service({"summary": "**Resultado:** Pidió que le llamaras.", "nextSteps": []})
    long_call = "You: hola, soy Ana de Acme\n\nThem: " + "estoy de vacaciones, llámame el lunes. " * 20
    out = asyncio.run(service.extract(long_call, SPECS, call_reading={"call_type": "not_a_sales_call"}))
    assert len(service.llm.calls) == 1 and out.summary.startswith("**Resultado:** Pidió")


def test_an_empty_grounded_reply_is_retried_once():
    class Flaky(FakeLLM):
        async def chat_json(self, messages, **kwargs):
            self.calls.append(messages)
            return {} if len(self.calls) == 1 else {"summary": "**Resultado:** Reunión el lunes.", "nextSteps": []}
    service = _service({})
    service.llm = Flaky({})
    out = asyncio.run(service.extract("You: hola soy Ana de Acme\n\nThem: vale, el lunes", SPECS, call_reading=READING))
    assert len(service.llm.calls) == 2 and out.summary.startswith("**Resultado:** Reunión")


def test_a_crm_fact_needs_the_prospects_own_words():
    from app.services.extraction import require_prospect_evidence
    transcript = "You: ¿Os cuesta generar leads?\n\nThem: Facturamos dos millones y usamos HubSpot desde hace años."
    out = require_prospect_evidence({
        "painPoints": ["Falta de leads"],
        "competitors": ["HubSpot"],
        "company_properties": {"annualrevenue": 2000000, "crm": "hubspot", "name": "Acme"},
        "contactName": "Ana",
        "evidence": {
            "painPoints": "Os cuesta generar leads",          # the rep's words: not the prospect's
            "competitors": "usamos HubSpot desde hace años",
            "company_properties.annualrevenue": "facturamos dos millones",
        },
    }, transcript)
    assert out["painPoints"] == [] and out["competitors"] == ["HubSpot"]
    assert out["company_properties"] == {"annualrevenue": 2000000, "crm": None, "name": "Acme"}
    assert out["contactName"] == "Ana" and "evidence" not in out


def test_evidence_paths_are_matched_loosely_and_list_items_can_back_themselves():
    from app.services.extraction import require_prospect_evidence
    transcript = "You: ¿Quién decide?\n\nThem: Eso lo decide mi socio Pablo. Ahora mismo no me interesa."
    out = require_prospect_evidence({
        "decisionMakers": ["Pablo"],
        "objections": ["no me interesa", "es caro"],
        "evidence": {"decisionMakers[0]": "lo decide mi socio Pablo"},
    }, transcript)
    assert out["decisionMakers"] == ["Pablo"]
    assert out["objections"] == ["no me interesa"]


def test_identity_written_at_the_top_fills_the_crms_own_empty_name_fields():
    from app.services.extraction import grounded_cleanup
    out = grounded_cleanup({
        "contactName": "Sergi Bonilla", "companyName": "Creantun Talent",
        "contact_properties": {"firstname": None, "lastname": None, "email": None},
        "company_properties": {"name": None, "crm": None},
    })
    assert out["contact_properties"]["firstname"] == "Sergi" and out["contact_properties"]["lastname"] == "Bonilla"
    assert out["company_properties"]["name"] == "Creantun Talent"
    kept = grounded_cleanup({"contactName": "Sergi", "contact_properties": {"firstname": "Sergio"}})
    assert kept["contact_properties"]["firstname"] == "Sergio"  # never overwrites


def test_a_fact_the_prospect_confirmed_or_said_across_a_turn_split_is_kept():
    from app.services.extraction import require_prospect_evidence
    transcript = (
        "You: He visto que sois una plataforma de gestión de flotas, ¿verdad?\n\n"
        "Them: Sí.\n\n"
        "You: Y os ayudamos a vender más, que es lo que hacemos.\n\n"
        "Them: Vale.\n\n"
        "You: ¿Qué tal estáis ahora?\n\n"
        "Them: Al final lo estamos haciendo internamente y no vamos a utilizar ningún tipo de\n\n"
        "You: asesoramiento externo para la planificación. Vale.\n\n"
        "Them: Más adelante, después de Black Friday podemos hablar, ahora estamos hasta arriba."
    )
    out = require_prospect_evidence({
        "company_properties": {"products_or_services_offered": "Gestión de flotas", "pains": "Vender más"},
        "objections": ["Lo hacen internamente", "No es el momento"],
        "evidence": {
            "company_properties.products_or_services_offered": "sois una plataforma de gestión de flotas",
            "company_properties.pains": "os ayudamos a vender más",  # a pitch answered "Vale": not confirmed
            "objections": [
                "lo estamos haciendo internamente y no vamos a utilizar ningún tipo de asesoramiento externo",
                "después de Black Friday podemos hablar... [Them:] ahora estamos hasta arriba",
            ],
        },
    }, transcript)
    assert out["company_properties"] == {"products_or_services_offered": "Gestión de flotas", "pains": None}
    assert out["objections"] == ["Lo hacen internamente", "No es el momento"]


def test_a_bare_yes_or_number_backs_a_field_only_next_to_the_question_it_answered():
    from app.services.extraction import require_prospect_evidence
    transcript = (
        "You: Vendéis B2B, todo tema consultiva, ¿verdad?\n\nThem: Sí.\n\n"
        "You: ¿Cuántos clientes tenéis?\n\nThem: 10. Más o menos.\n\n"
        "You: ¿Usáis HubSpot?\n\nThem: Sí.\n\n"
        "You: Sois un SaaS de IA para informes, ¿verdad?\n\nThem: Sí, más o menos.\n\n"
        "You: ¿Y de CRM?\n\nThem: Sí, HubSpot."
    )
    out = require_prospect_evidence({
        "company_properties": {
            "products_or_services_offered": "B2B, todo tema consultiva",
            "number_of_clients": 10,
            "numberofemployees": 25,
            "sector": "Logística",
            "industry": "SaaS de IA para informes",
            "crm": "hubspot",
        },
        "evidence": {
            "company_properties.products_or_services_offered": "Sí.",
            "company_properties.number_of_clients": "10.",
            "company_properties.numberofemployees": "25",
            "company_properties.sector": "Sí.",
            "company_properties.industry": "Sí, más o menos. [en respuesta a: SaaS de IA para informes]",
            "company_properties.crm": "Sí, HubSpot.",
        },
    }, transcript)
    assert out["company_properties"] == {
        "products_or_services_offered": "B2B, todo tema consultiva", "number_of_clients": 10,
        "numberofemployees": None, "sector": None, "industry": None,
        "crm": "hubspot",
    }


def test_decision_makers_need_the_prospect_saying_who_decides():
    from app.services.extraction import require_prospect_evidence
    transcript = (
        "You: ¿Tú eres el fundador?\n\nThem: Sí, soy Oriol, el fundador.\n\n"
        "You: ¿Y lo veríais solo tú?\n\nThem: No, eso lo tengo que hablar con mi socio Pablo."
    )
    kept = require_prospect_evidence({
        "decisionMakers": ["Oriol", "Pablo"],
        "evidence": {"decisionMakers": "eso lo tengo que hablar con mi socio Pablo"},
    }, transcript)
    assert kept["decisionMakers"] == ["Oriol", "Pablo"]
    dropped = require_prospect_evidence({
        "decisionMakers": ["Oriol"],
        "evidence": {"decisionMakers": "Sí, soy Oriol, el fundador"},
    }, transcript)
    assert dropped["decisionMakers"] == []
