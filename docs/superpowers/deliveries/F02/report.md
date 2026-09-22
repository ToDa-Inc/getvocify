# Informe F02

Estado: código de C03 en la rama `feat/vocify-v1`. El esquema ya está aplicado.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Reglas puras: buzón no genera borrador; `sent` es apertura, no entrega | `8f3ca92` | `tests/test_followup_logic.py` 9 passed |
| Migración `038_memos_followup.sql` | `8f3ca92` | Columnas en `full_reset.sql` |
| Generación en segundo plano, un solo vuelo, fallo = `unavailable` | `1a81474` | `tests/test_followup_service.py` 6 passed |
| Se programa tras extracción, reextracción y WhatsApp. El buzón de voz no | `a161627` | Tres llamadas a `schedule_followup` |
| GET para quien puede leer; POST solo el autor; manager `403`; no listo `409` | `2166650` | `tests/test_followup_api.py` 3 passed |
| `<v-followup>` y hoja compartida | `bfa1ae3` | `shared/ui/ui.test.js` 14 passed |
| Extensión, desktop y web | `5b3b5a8`, `61ba0e7`, `ee4ee7b` | `npm run build` en verde para la web |

## No verificado

- No hay un memo real de HubSpot, desktop o WhatsApp recorrido de punta a punta.
- Reticle no se ejecutó sobre `/dashboard/memos/:id`.
- La migración `038` no se ha aplicado en producción ni en una base compartida.

## Contrato C03

`status` es `generating|ready|sent|unavailable`. `sent` significa que el borrador se abrió en el correo o en WhatsApp. Un teléfono sin `+` no se ofrece para WhatsApp.
