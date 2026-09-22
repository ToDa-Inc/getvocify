# Informe F13

Estado: la instantánea del periodo separa intentos, conversaciones y cierres. No está cerrada.

## Entregado

| Pieza | Prueba |
|---|---|
| Un buzón cuenta como intento y no como conversación. Una reunión acordada no suma un cierre | `tests/reporting/test_aggregate.py` |
| Si el CRM no demuestra el cierre, `deals_won` es null y la cobertura es `unavailable`, no 0 | el mismo archivo |
| Un periodo vacío deja los conteos en 0, la adherencia vacía y sin texto de coaching | el mismo archivo, 2 passed |

La fecha que cuenta es la de la captura, no la del trabajo que termina después.

## No verificado

- No hay migración `048`, ni envío de email, ni campana, ni página del informe.
- Los proveedores no leen todavía los cierres reales del periodo.
