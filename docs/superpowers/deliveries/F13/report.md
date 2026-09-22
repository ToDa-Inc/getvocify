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

## No verificado

- `GET /reports/{id}` devuelve la instantánea guardada. El informe de otra persona responde 404. Marcar la campana dos veces conserva la primera hora. La página está en `/dashboard/reports/:id`. No se recorrió en el navegador.
- El correo no se envía de verdad: Resend solo acepta la clave de idempotencia si alguien la pasa. La campana no está en la barra.
- Los proveedores no leen todavía los cierres reales del periodo.
