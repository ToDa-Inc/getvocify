import assert from "node:assert/strict";
import test from "node:test";
import { askActivitySummary, askCoverageText, askToolLabel, productCatalog } from "./product-catalog.ts";

const en = productCatalog.EN;
const es = productCatalog.ES;

test("every Ask string exists in both languages", () => {
  const missing = Object.keys(en).filter((k) => k.startsWith("ask") && !(k in es));
  assert.deepEqual(missing, []);
  const extra = Object.keys(es).filter((k) => k.startsWith("ask") && !(k in en));
  assert.deepEqual(extra, []);
});

test("tool labels never show the internal tool name", () => {
  assert.equal(askToolLabel("deal_story", es), "Leyendo las conversaciones con este contacto");
  assert.equal(askToolLabel("something_new", es), "Trabajando");
});

test("activity summary handles singular and plural", () => {
  assert.equal(askActivitySummary(1, en), "Looked at 1 source");
  assert.equal(askActivitySummary(3, en), "Looked at 3 sources");
});

test("coverage wording differs for partial, forbidden and unavailable", () => {
  assert.equal(askCoverageText({ level: "partial", n: 14, n_analysed: 6 }, en), "Based on 6 of 14 conversations. The rest aren't analysed yet.");
  assert.equal(askCoverageText({ level: "partial" }, en), "Based on partial data.");
  assert.notEqual(askCoverageText({ level: "forbidden" }, en), askCoverageText({ level: "unavailable" }, en));
});

test("coverage wording follows what was read: conversations, calls or deals", () => {
  assert.equal(askCoverageText({ level: "partial", n: 100, n_analysed: 40, unit: "calls" }, en), "Only 40 of 100 calls have an outcome logged in HubSpot.");
  assert.equal(askCoverageText({ level: "partial", n: 26, n_analysed: 23, unit: "deals" }, es), "23 de 26 deals perdidos tienen motivo en HubSpot.");
  assert.match(askCoverageText({ level: "partial", n: 14, n_analysed: 6 }, es), /6 de 14 conversaciones/);
});

test("a partial HubSpot query says how many records it read, not that deals lack a reason", () => {
  assert.equal(askCoverageText({ level: "partial", n: 2400, n_analysed: 1000, unit: "records" }, en), "Worked out from 1000 of 2400 records in HubSpot.");
  assert.equal(askCoverageText({ level: "partial", n: 2400, n_analysed: 1000, unit: "records" }, es), "Calculado con 1000 de 2400 registros de HubSpot.");
});

test("a period the tool chose is stated on its own or after the coverage line", () => {
  assert.equal(askCoverageText({ level: "period", period_days: 90 }, en), "Last 90 days.");
  assert.equal(askCoverageText({ level: "period", period_days: 30 }, es), "Últimos 30 días.");
  assert.equal(askCoverageText({ level: "partial", n: 14, n_analysed: 6, period_days: 30 }, es), "Basado en 6 de 14 conversaciones. El resto aún no está analizado. Últimos 30 días.");
  assert.equal(askCoverageText({ level: "partial", period_days: 30 }, en), "Based on partial data. Last 30 days.");
});

test("every tool the server can offer has a readable label in both languages", () => {
  const tools = ["deal_story", "find_interactions", "objection_breakdown", "next_actions", "my_coaching", "team_health", "competitor_mentions", "meetings_agreed", "playbook_lookup", "crm_call_stats", "crm_lost_reasons", "hubspot_describe", "hubspot_query"];
  for (const tool of tools) {
    assert.notEqual(askToolLabel(tool, en), en.askToolFallback, `EN ${tool}`);
    assert.notEqual(askToolLabel(tool, es), es.askToolFallback, `ES ${tool}`);
  }
});

test("every suggestion id the server can send has copy in both languages", () => {
  for (const id of ["next_actions", "my_coaching", "team_health", "objections", "connection_rate", "lost_reasons", "playbook"]) {
    assert.ok((en as Record<string, string>)[`askSuggest_${id}`], `EN ${id}`);
    assert.ok((es as Record<string, string>)[`askSuggest_${id}`], `ES ${id}`);
  }
});
