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

Verificación registrada por el **controlador** el **24 sep 2026** (no se invocaron herramientas de actualización de Railway en esta tarea):

| Campo | Valor |
|---|---|
| Servicio | `getvocify` |
| Entornos | `prod`, `production` |
| Watch Paths | `/backend/**` |

Nota: `get_service_config` vía MCP en el worktree no estaba enlazado a un proyecto Railway; la comprobación operativa queda anclada a la verificación del controlador anterior.

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
| Railway watch paths | ok (verificado controlador) |
| desktop `npm test` | 88/88 pass |
| shared/ui tests | 69/69 pass |
| sync-shared `--check` | ok |

No se detectaron tests en rojo previo en esta línea base.

## Notas

- Cambios locales no relacionados en `backend/` permanecen **sin stage** (materialize, aggregate, adherence tests).
- Próximas tareas: host macOS nativo y UX según el plan DESKTOP-MAC.
