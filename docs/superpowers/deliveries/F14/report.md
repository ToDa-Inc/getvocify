# Informe F14

Estado: la propuesta de reunión no inventa la hora. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| «Podríamos vernos» no es acuerdo; la hora de subida no es la cita; acordar no cierra el deal | `tests/meetings/test_proposals.py` |
| 16:00 corregido y confirmado por ambos queda en las 17:00 de Madrid (15:00 UTC), con la evidencia de la corrección | el mismo archivo |
| «A las cinco» sin contexto queda ambiguo, no 17:00. La hora duplicada del cambio de horario pide revisión | el mismo archivo |
| Migración `046`: una propuesta ambigua se guarda con `starts_at` vacío | Postgres aislado, 5 passed |

## No verificado

- Aceptar la propuesta no escribe todavía en HubSpot ni en Pipedrive.
- No cambia la etapa del deal.
- No está en la pantalla de revisión.
