# Informe F08

Estado: cerrado contra DoD en `feat/vocify-v1`, salvo recorrido manual en Settings.

## Criterios DoD (plan 04-f08-playbooks.md §163–177)

| Criterio | Evidencia |
|---|---|
| Texto, PDF y audio → borrador revisable | `test_text_becomes_a_revisable_draft`, `test_a_real_pdf_becomes_a_draft…`, `test_audio_becomes_a_draft_without_a_crm_memo` |
| Member lee, no escribe | `test_member_can_read_playbooks_but_cannot_import`, publish 403 en `test_publishing_discovery…` |
| Tipología sin deploy | `test_adding_a_typology…`, `add_interaction_type` en Postgres aislado |
| Error de importación no sustituye activa | `test_empty_pdf…`, PDF cifrado; `playbook-setup.test.ts` |
| Entrada con `source_ref` | `test_member_cannot_publish_and_an_entry_needs_a_source`, fila Postgres |
| UI manual sin entrevista IA | `playbook-setup.test.ts` (PlaybooksSection solo `/playbooks/*`) |
| Empresa nueva: aviso y flujo completo; member sin controles | **Bloqueado:** requiere Reticle o recorrido humano en Settings → Proceso comercial |
| Borrador mantiene aviso; coaching off; una tipología no publica las demás | `playbook-setup.test.ts`, `coaching-score.test.ts`, `test_unpublished_playbook_is_explicitly_absent` |

## Bloqueadores humanos / Reticle

- **DoD §167:** no hay sesión Reticle en este worktree. Falta verificar en navegador que una empresa vacía ve el aviso, un owner recorre tipología → contenido → revisión → publicación, y un member ve la explicación sin textarea ni botones de guardar/publicar/añadir tipología.

## Reglas ya verificadas (commits previos de la rama)

- Una versión activa; captura fija la versión del inicio.
- Member no publica; entrada sin fuente no se publica.
- Publicar discovery no publica qualification.
- PDF sin texto no publica; audio borrador sin memo.
- pypdf + STT inyectable en tests HTTP sin arrancar API.

## Limitaciones documentadas

- La pantalla envía PDF en base64; no hay OCR.
- Tests HTTP de import usan almacén en memoria salvo el bloque Postgres de `test_two_publishes…`.
