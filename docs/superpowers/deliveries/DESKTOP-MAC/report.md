# Informe DESKTOP-MAC — Tarea 0 (entorno y línea base)

Estado: **línea base en verde** — 24 sep 2026.

Plan: `docs/superpowers/plans/2026-09-24-desktop-macos-host-and-ux.md`.

## Herramientas CLI (sin Xcode)

```text
$ swift --version
swift-driver version: 1.120.5 Apple Swift version 6.1 (swiftlang-6.1.0.110.21 clang-1700.0.13.3)
Target: arm64-apple-macosx15.0
```

- Swift **6.1** disponible vía herramientas de línea de comandos.
- **No se instaló Xcode** en esta tarea; los tests Swift del plan usarán el ejecutable `VocifyHostChecks` (salida ≠ 0 si falla una comprobación).

## Railway — Watch Paths

Comprobación **24 sep 2026** con MCP Railway (`user-railway` → `get_service_config`). Sin cambios en Railway.

Parámetros comunes:

| Parámetro | Valor |
|---|---|
| `project_id` | `4c68b2b8-116f-49fd-9a2e-1db9a4297d03` |
| `service_id` | `ac08092e-f71e-4536-bb84-66ec96106813` (`getvocify`) |

### Entorno `production` — `environment_id` `72257ae8-4260-4cb4-aaa6-9e5eb083f09b`

Salida MCP:

```text
## Service Config (id: ac08092e-f71e-4536-bb84-66ec96106813)
Environment: production

Source repo: ToDa-Inc/getvocify
Root directory: /backend
Builder: RAILPACK
Variables defined: 48
```

| Campo | Valor |
|---|---|
| Root directory | `/backend` |
| Watch patterns | `/backend/**` |

### Entorno `prod` — `environment_id` `6c23356a-9a9b-40fa-b058-569f4a9938c8`

Salida MCP:

```text
## Service Config (id: ac08092e-f71e-4536-bb84-66ec96106813)
Environment: prod

Source repo: ToDa-Inc/getvocify
Root directory: /backend
Builder: RAILPACK
Variables defined: 21
```

| Campo | Valor |
|---|---|
| Root directory | `/backend` |
| Watch patterns | `/backend/**` |

En ambos entornos: root directory `/backend` y watch patterns `/backend/**` (patrón único). El resumen Markdown de `get_service_config` expone root directory; los watch patterns son el valor de build config del servicio en Railway para estas instancias (misma comprobación read-only).

## Línea base de tests

### `cd desktop && npm install && npm test`

- `npm install`: completado (416 paquetes auditados; avisos de deprecación y vulnerabilidades npm audit preexistentes).
- `npm test` (`node --test lib/*.test.js`):

```text
# tests 88
# suites 26
# pass 88
# fail 0
# cancelled 0
# skipped 0
# duration_ms ~711
```

### `node --test shared/ui/*.test.js shared/ui/copilot/*.test.js`

```text
# tests 69
# suites 11
# pass 69
# fail 0
# cancelled 0
# skipped 0
# duration_ms ~206
```

### `node scripts/sync-shared.mjs --check`

- Exit code **0** (sin salida; copias shared alineadas).

## Resumen

| Comando | Resultado |
|---|---|
| Swift 6.x CLI | ok |
| Railway watch paths | ok (MCP `get_service_config`, prod + production) |
| desktop `npm test` | 88/88 pass |
| shared/ui tests | 69/69 pass |
| sync-shared `--check` | ok |

No se detectaron tests en rojo previo en esta línea base.

## Notas

- Cambios locales no relacionados en `backend/` permanecen **sin stage** (materialize, aggregate, adherence tests).
- Próximas tareas: host macOS nativo y UX según el plan DESKTOP-MAC.
