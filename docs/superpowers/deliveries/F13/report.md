# Informe F13

Estado: la instantánea del periodo separa intentos, conversaciones y cierres. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Un buzón cuenta como intento y no como conversación. Una reunión acordada no suma un cierre | `tests/reporting/test_aggregate.py` |
| Si el CRM no demuestra el cierre, `deals_won` es null y la cobertura es `unavailable`, no 0 | el mismo archivo |
| Un periodo vacío deja los conteos en 0, la adherencia vacía y sin texto de coaching | el mismo archivo, 2 passed |

La fecha que cuenta es la de la captura, no la del trabajo que termina después.

| Un periodo local es un solo informe aunque cambie el horario; el correo fallido conserva la campana; un timeout no reenvía | `tests/reporting/test_delivery.py` 3 passed; migración `048` |

La ruta de producción `send_report_email` usa el adaptador Resend cuando el caller inyecta cliente Resend (sin envío real verificado en vivo).

`run_due_report_emails` enlaza `due_report_sends` con `send_report_email` (sender falso en tests; sin envío en vivo ni bucle en `main`).

## No verificado

- `GET /reports/{id}` devuelve la instantánea guardada. El informe de otra persona responde 404. Marcar la campana dos veces conserva la primera hora. La página está en `/dashboard/reports/:id`. No se recorrió en el navegador.
- La campana está en la barra. El número solo aparece si hay informes sin leer. Un fallo de lectura no pinta un cero.
- Los proveedores no leen todavía los cierres reales del periodo.
