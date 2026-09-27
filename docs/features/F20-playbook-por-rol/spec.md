# Spec · F20 — Playbook según el rol

> Pieza 5 de 6. Puerta: `SALES_ROLES_ENABLED`.

## Job
El SDR trabaja con el proceso de prospección y el AE con el de cierre. El administrador sigue viendo y editando los tres.

## Reglas
1. SDR ve en Proceso: Descubrimiento y Calificación.
2. AE ve en Proceso: Cierre.
3. Ambos, owner y admin ven los tres.
4. Si una captura no trae `sales_motion_key` y el flag está encendido, se rellena: SDR → `discovery`, AE → `closing`, Ambos → no se impone.
5. Flag apagado: Proceso enseña los tres y la captura no rellena el motion.
6. La configuración de etapas de F16 sigue solo para owner/admin.

## Edge cases
| # | Caso | Esperado |
|---|---|---|
| P1 | SDR abre Proceso | No ve Cierre |
| P2 | AE abre Proceso | Solo Cierre |
| P3 | Admin | Los tres, y el bloque de etapas |
| P4 | Captura de un SDR sin motion | `discovery` |
| P5 | Flag apagado | Sin filtro y sin motion automático |
