# Prompt de revisión — ejecución de Vocify V1 (`feat/vocify-v1`)

> Pega esto como instrucción inicial de una sesión nueva, con contexto limpio. No asumas que lo implementado funciona porque los planes dicen "DoD cerrado" — eso está por verificar, no por confirmado.

## 1. Qué se revisa

El código está en el worktree `/Users/danizal/getvocify/.worktrees/vocify-v1`, rama `feat/vocify-v1`, commit `eeaea3d`. Diff contra `main`: 525 archivos, ~58.200 líneas insertadas. Implementa F0, F0.1 y F01–F15 (las 15 features de `proposed_plan.md`), cada una cerrada con su propio commit "close DoD" y sus tests.

**Premisa de esta revisión:** el usuario reporta que, aunque el plan se ejecutó de principio a fin, el resultado no es funcional del todo y hay problemas de UX/UI y de coherencia de frontend. Tu trabajo es encontrar exactamente qué, no confirmar que todo está bien.

## 2. Fuentes, en este orden

1. `docs/superpowers/plans/2026-09-22-vocify-v1/00-contracts.md` y `00-integration-and-gates.md` — contratos entre features y puertas de integración. Léelos primero, son el pegamento entre todas las demás.
2. `docs/superpowers/plans/2026-09-22-vocify-v1/README.md` — mapa de las 16 entregas y su orden.
3. `docs/superpowers/plans/2026-09-22-vocify-v1/0N-fXX-*.md` — el plan individual de cada feature, con su Definition of Done. Es contra esto que se implementó; es contra esto que evalúas.
4. `docs/PLAN_UPDATE_INSTRUCTIONS_VOCIFY.md` — checklist de UX/integración (bloques A y B) que debía incorporarse al plan antes de ejecutar. Verifica cuáles de esos puntos entraron de verdad en el código y cuáles no.
5. `proposed_plan.md` — plan maestro, solo si un plan individual remite a él y no está claro sin leerlo.
6. `docs/PRODUCT_PLANNING_ANALYSIS_2026-09-21.md` — contexto de producto, solo si necesitas el porqué de una decisión que no está explicado en los planes de ejecución.

No leas las 58.200 líneas del diff de una sola vez. Trabaja feature por feature: plan individual → diff de los archivos que ese plan dice tocar → verificación en vivo de esa feature.

## 3. Cómo verificar — no te quedes en leer código

- Levanta el dashboard web desde el worktree: `.worktrees/vocify-v1/.claude/launch.json` ya tiene la config `vocify-web` (`npm run dev`, puerto 8080). Úsala con `preview_start`, no compongas el comando a mano.
- El desktop (`getvocify-desktop`) y la extensión de Chrome no tienen config de lanzamiento en ese `launch.json` — revísalos por separado (leer código +, si puedes montarlos, probarlos) y dilo explícitamente si no pudiste ejecutarlos, no lo des por verificado.
- Para cada feature: dirígela de verdad en el navegador (Reticle si aplica, o `computer`/`Claude_Browser` para clicar), no solo confirmes que el endpoint existe o que el componente está importado.
- Un test unitario en verde no es lo mismo que la feature funcionando en la UI real — el propio historial de commits de esta rama ("close DoD con tests") es evidencia de tests, no de verificación funcional. Trátalo así.

## 4. Qué producir, por feature (F0, F0.1, F01–F15)

Para cada una:
1. **¿Coincide lo implementado con su plan individual?** Cita el archivo del plan y la sección de DoD, y el archivo/línea real donde se implementó o donde falta.
2. **¿Funciona de verdad al usarlo?** Estado real observado, no inferido del código.
3. **¿Qué puntos de `PLAN_UPDATE_INSTRUCTIONS_VOCIFY.md` le aplicaban y se cumplieron o no?** (ej. F12 debía reutilizar el overlay existente de `getvocify-desktop/electron-main.mjs` en vez de una tarjeta dentro de la ventana principal — confirma cuál de las dos se construyó).
4. **Severidad de cada hallazgo:** rompe el flujo / funciona pero mal / desviación menor de UX / cosmético.

Además, a nivel transversal (no por feature):
- **Coherencia de frontend:** ¿se usó el kernel de UI compartido (`shared/ui/`) donde correspondía, o hay implementaciones duplicadas/inconsistentes por feature? ¿los estilos nuevos respetan `src/styles/tokens.css`? ¿hay pantallas que no siguen "menos clicks, más valor" (texto/botones de más, pasos innecesarios)?
- **AI slop:** cualquier texto generado por IA visible al usuario (follow-up, brief, reason/due_label de "Hoy", sugerencias de F12) — ¿es corto y directo, o genérico?
- **Qué del plan original quedó sin construir**, aunque su commit diga "DoD cerrado" — sé explícito si encuentras checkboxes marcados que no corresponden a algo verificable en la app real.

## 5. Reglas

- No inventes veredictos — todo hallazgo cita archivo/línea o el paso exacto que lo reprodujo.
- No asumas que algo funciona por estar en el código — ejecútalo.
- Si algo no se pudo verificar (ej. desktop/extensión sin entorno para correrlos), dilo como limitación de la revisión, no como aprobado.
- Prioriza los hallazgos: qué rompe el uso real primero, qué es cosmético al final.

## 6. Formato de salida

Un hallazgo por fila, ordenado por severidad, con: feature, archivo/línea, qué se esperaba (según el plan), qué se observó (código y/o comportamiento real), severidad. Cierra con un resumen de qué features están realmente usables hoy y cuáles no.
