# Spec · F21 — El administrador ve el Hoy del equipo

> Pieza 6 de 6. Puerta: `SALES_ROLES_ENABLED`. El administrador es owner o admin. No es un rol de HubSpot.

## Job
El head of sales abre Hoy y ve las llamadas y las reuniones del equipo, con el nombre de quién las tiene.

## Reglas
1. Owner y admin no quedan encerrados en un solo rol: ven «Llamadas» y «Reuniones».
2. Con el flag encendido, su Hoy junta las señales de la empresa, no solo las suyas. Cada tarjeta lleva el nombre del comercial.
3. `ended` sigue oculto.
4. Máximo 7 por lista.
5. Flag apagado: su Hoy sigue siendo solo el suyo, como ahora.
6. Equipo y las notas con alcance de empresa no se rehacen.

## Edge cases
| # | Caso | Esperado |
|---|---|---|
| A1 | Admin, flag encendido, señal de un SDR | Sale en Llamadas con el nombre del SDR |
| A2 | Admin, reunión de un AE | Sale en Reuniones con el nombre del AE |
| A3 | Member SDR | No ve las señales de otro |
| A4 | Flag apagado | El admin solo ve las suyas |
