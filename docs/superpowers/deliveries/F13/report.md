# Informe F13

Estado: **BLOCKED** — falta el layout A12 completo (informe semanal con barras y tabla equivalente) y verificación Reticle campana → informe.

## Criterio de aceptación

| Criterio | Prueba |
|---|---|
| Email y campana muestran los mismos números | `tests/reporting/test_presentation.py`, `tests/reporting/test_report_read.py::test_bell_item_opens_the_same_snapshot_the_email_table_uses` |
| Un periodo, un informe | `tests/reporting/test_delivery.py::test_two_workers_insert_one_report_for_the_period`, `tests/reporting/test_ensure_daily_report_from_memos.py` (upsert) |
| Reintentar envío no duplica notificaciones | `tests/reporting/test_ensure_daily_report_from_memos.py::test_failed_email_retry_next_day_does_not_duplicate_notification` |
| Cambios horarios (DST) | `tests/reporting/test_delivery.py::test_dst_is_one_period_and_a_failed_email_keeps_the_notification` |
| Sin métricas ajenas | `tests/reporting/test_report_read.py`, `tests/reporting/test_delivery.py::test_the_bell_counts_only_unread_rows_for_this_user` |
| Email fallido conserva campana | mismo test DST + `notification.kept` en `deliver_report` |
| Enlaces a conversaciones, sin coaching inventado | `tests/reporting/test_presentation.py`, `src/lib/report-snapshot.test.ts`, `examples` en snapshot |
| Layout diario A12 + semanal con barras | **Pendiente** — `ReportPage.tsx` solo tabla diaria; no hay `report_type=weekly`, `ReportActivityChart` ni secciones A12 (cabecera, objeciones, coaching estructurado) |
| Periodo vacío / cobertura parcial | `tests/reporting/test_aggregate.py`, `tests/reporting/test_presentation.py`, `report-snapshot.test.ts` |

## Entregado (backend)

- Instantánea: intentos ≠ conversaciones; `deals_won` null sin CRM; periodo vacío sin coaching (`test_aggregate.py`).
- Materialización diaria antes del tick; `capture_started_at`; una notificación por informe (`test_ensure_daily_report_from_memos.py`, 6+ casos).
- Tick 18:00 Madrid; `sent`/`uncertain` no reenvían; `failed` como mucho una vez por día local vía `created_at` (`test_due_sends.py`, `test_tick_due_report_emails.py`).
- Email HTML desde la misma instantánea persistida (`presentation.py`, `_ReportIdSender`); sin envío Resend real en CI.
- Destinatario ausente → `failed`, no `sent` (`test_tick_bindings.py`).

## Bloqueos

1. **Layout A12 / informe semanal:** no hay generación de informe semanal ni gráfico de barras con huecos; la casilla de layout queda abierta.
2. **Reticle:** no hay sesión conectada; no se verificó campana → `/dashboard/reports/:id` en navegador (`verified: pass` pendiente).
3. **CRM en vivo:** cierres reales del periodo no leídos de HubSpot/Pipedrive en producción (deferred F15); `deals_won` sigue null salvo cobertura completa en tests.
