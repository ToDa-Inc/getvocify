# Spec · F18 — El estado «sale del SDR» entra en el AE

> Pieza 3 de 6. Depende de F16 (el estado) y F17 (la cuenta). Solo actúa con `SALES_ROLES_ENABLED`.

## Job
Cuando el contacto queda en una etapa marcada como «sale del SDR», deja la lista de llamadas del SDR y pasa a la lista de reuniones de quien lo tiene en el CRM, si esa cuenta es AE o Ambos.

## Reglas
1. `ended` no lo ve nadie en Hoy ni en la cola.
2. `booked` no está en la cola de llamadas de un SDR ni de Ambos.
3. `booked` sí está en las reuniones del usuario cuyo propietario en el CRM es él, si su rol es `ae` o `general`.
4. Si el propietario en el CRM sigue siendo un SDR, el contacto no vuelve a su lista de llamadas. El administrador lo ve en su Hoy (pieza 6).
5. La tarjeta de reunión enlaza la última nota de esa empresa sobre ese contacto, para que el AE lea lo que dijo el SDR. Si no hay nota, la tarjeta sale igual.
6. Con el flag apagado, F16 manda: `booked` y `ended` salen de la cola y de Hoy para todos.

## Edge cases
| # | Caso | Esperado |
|---|---|---|
| H1 | Flag apagado, estado booked | Fuera de Hoy y de la cola, como F16 |
| H2 | SDR, estado booked | Fuera de su cola y de su Hoy |
| H3 | AE dueño en el CRM, estado booked | En sus reuniones, no en su cola de llamadas |
| H4 | AE, estado vacío | No está en sus reuniones ni en su cola |
| H5 | Ambos, estado booked | Solo en reuniones |
| H6 | Ambos, sin estado de salida | Solo en llamadas |
| H7 | ended | Oculto para SDR, AE y Ambos |
| H8 | No hay nota del contacto | La reunión se muestra sin enlace |
