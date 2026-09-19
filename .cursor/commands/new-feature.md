# /new-feature — Scaffolding de una feature del plan maestro

Dado un ID de feature (ej.: `A3`, `B6`, `C1`) del `docs/features/MASTER_PLAN.md`:

1. Crea `docs/features/<ID>/` copiando las tres plantillas de `docs/features/_TEMPLATE/` (teardown.md, spec.md, design.md), sustituyendo `<ID>` y `<Nombre>` por los del plan maestro.
2. Pre-rellena en el teardown los competidores de referencia que el MASTER_PLAN y `~/vocify-features-master-list.md` citan para esa feature (con sus URLs).
3. Pre-rellena en el spec: el job-to-be-done borrador según la descripción del plan maestro, la audiencia (rep/manager) y una propuesta de métrica de calidad con umbral — márcala como PROPUESTA para que los founders la validen.
4. Crea la carpeta `backend/evals/<ID>/` con un `README.md` que explique qué casos necesita el dataset (mínimo 20).
5. NO escribas código de implementación. El output de este comando es solo el scaffolding para las etapas 1–3.
6. Termina listando los 3 documentos creados y qué debe completar cada founder antes de pasar a build.
