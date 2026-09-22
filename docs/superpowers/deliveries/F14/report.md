# Informe F14

Estado: la propuesta de reunión no inventa la hora. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| «Podríamos vernos» no es acuerdo; la hora de subida no es la cita; acordar no cierra el deal | `tests/meetings/test_proposals.py` |
| 16:00 corregido y confirmado por ambos queda en las 17:00 de Madrid (15:00 UTC), con la evidencia de la corrección | el mismo archivo |
| «A las cinco» sin contexto queda ambiguo, no 17:00. La hora duplicada del cambio de horario pide revisión | el mismo archivo |
| Migración `046`: una propuesta ambigua se guarda con `starts_at` vacío | Postgres aislado, 5 passed |
| Repetir la aprobación crea una actividad; un timeout se reconcilia antes de otro alta; sin mapeo de etapa no se cambia el deal | `tests/meetings/test_writes.py` 3 passed, Postgres aislado |
| La revisión no inventa fecha mientras extrae, no ofrece guardar sin acuerdo, no dice guardada si el CRM está incierto, y no se muestra en la llamada | `shared/ui/meeting-proposal.test.js` 3 passed |

## No verificado

- La revisión del memo carga la propuesta guardada. Si no hay fila, no se ofrece guardar. Al aceptar la reunión, `meetings/crm_writer.py` puede publicar una actividad en HubSpot o Pipedrive con el `access_token` de la conexión (adaptador inyectado en `register_meeting`).
