# Spec · F19 — Hoy según el rol

> Pieza 4 de 6. Misma puerta que F18: `SALES_ROLES_ENABLED`.

## Job
Cada comercial abre Hoy y ve el trabajo de su rol, no el de otro.

## Reglas
1. SDR: una sola lista, «Llamadas». Sin reuniones agendadas ni cierres.
2. AE: una sola lista, «Reuniones». Sin la cola de prospección.
3. Ambos: las dos listas, en ese orden, con esos títulos.
4. Flag apagado: Hoy se ve como hoy, una sola lista, sin títulos nuevos.
5. Máximo 7 tarjetas por lista.

## Edge cases
| # | Caso | Esperado |
|---|---|---|
| Y1 | SDR con llamadas y una reunión | Solo las llamadas |
| Y2 | AE con llamadas y una reunión suya | Solo la reunión |
| Y3 | Ambos con las dos | Dos bloques |
| Y4 | Flag apagado | Sin bloques nuevos |
