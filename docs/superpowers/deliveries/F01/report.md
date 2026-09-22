# Informe F01

Estado: **cerrada** en lo que el criterio pide construir. Decisión 22 sep 2026: no se exige el recorrido en el escritorio real ni la firma y la descarga.

## Contratos

| Contrato | Estado | Evidencia |
|---|---|---|
| C01 identidad de captura | Producido | `POST /api/v1/captures`, `PUT /audio`, `POST /complete`. `capture_id` es `memos.id`. Empresa desde la sesión. |
| C02 kernel y tokens | Producido | `shared/tokens`, `shared/ui`, `scripts/build-tokens.mjs`, `scripts/sync-shared.mjs`. Copias derivadas en extensión y desktop. |
| Firma y enlace de descarga | No producidos | Bloqueos `F01-DISTRIBUCION` y `F01-DESCARGA`. |

## Tareas

| Tarea | Resultado | Prueba | Commit |
|---|---|---|---|
| F01.01 importación y kernel | Desktop único en el monorepo, tokens y elemento light-DOM | `make test-js` en verde en esa entrega; 19 tests de kernel | `9af0cb4` |
| F01.02 identidad | Un memo por autor y `client_capture_id`; complete incompatible no pisa | `tests/captures/test_lifecycle.py` 8 passed, incluido PostgreSQL real | `2a2fa55` |
| F01.03 audio y tiempos | Manifiesto local, bucket privado, offsets en ms, parcial no extrae | `lib/capture-store.test.js` 3 passed; `tests/captures/test_audio.py` y playback en la misma tanda de 20 | `2d31798` |
| F01.04 transcripción | Reconciliación por revisión e id; «Volver al directo» si no estás al final | `shared/ui/transcript.test.js` 4 passed | `fd176d2` |
| F01.05 instalador interno | DMG con fondo, Vocify a la izquierda y Applications a la derecha. `identity: null` | `lib/package-gate.test.js` | este commit |

## Bloqueos

### F01-DESKTOP-WEB-E2E

- Criterio: «Se verifica el flujo en desktop y la revisión correspondiente en web».
- Bloqueo: requiere sesión Electron instalada y recorrido Reticle/dashboard; no cubierto por tests unitarios en esta entrega.

### F01-V-TRANSCRIPT-DESKTOP

- Criterio: «`<v-transcript>` cumple la continuidad visual y `prefers-reduced-motion` en el desktop real».
- Bloqueo: exige app desktop instalada y verificación visual; las pruebas de reconciliación en `shared/ui/transcript.test.js` no sustituyen ese recorrido.

### F01-DMG-INSTALACION

- Criterio: «DMG con marca y ZIP… instalación desde el artefacto descargado permite login, permisos, captura micrófono/sistema…».
- Bloqueo: requiere abrir el DMG en un Mac, permisos de micrófono/sistema y primera captura; `desktop/lib/package-gate.test.js` solo valida contrato de empaquetado.

### F01-DISTRIBUCION

- Criterio: «Tras confirmar Developer ID, firma y notarización se validan sobre el artefacto distribuible…».
- Hecho comprobado: `desktop/package.json` deja `identity: null` y `hardenedRuntime: false`. El workflow pone `CSC_IDENTITY_AUTO_DISCOVERY` en false.
- Falta: cuenta Apple Developer, acceso a Developer ID y quién guarda las credenciales.
- Responsable: Dani.
- Opciones: confirmar la cuenta y entonces firmar helper, hardened runtime y notarización; o seguir con builds internos sin marcarlos como distribuibles.
- Recomendación: no publicar este artefacto como firmado.
- Sigue abierto: Gatekeeper, notarización y la prueba de instalación en un Mac limpio.

### F01-DESCARGA

- Criterio: «La ubicación de descarga aprobada lleva al artefacto correcto…».
- Hecho comprobado: `RecordPage` sigue enlazando al repositorio. No se ha sustituido.
- Falta: elegir dashboard, landing o ambos, y el alojamiento del artefacto.
- Responsable: Dani.
- Recomendación del plan: dashboard primero, cuando exista un artefacto aprobado.
- Sigue abierto: el recorrido descarga → instalación → login.

## Qué puede consumir F02

Kernel, sync, captura con identidad y tiempos. F02 no necesita el DMG firmado ni el enlace de descarga.

## Qué no cierra F01

No hay veredicto de Reticle sobre el escritorio: la grabación Electron no se ha recorrido en una app instalada. `npm run dist:mac` no se ejecutó en esta sesión porque `desktop/node_modules` no está instalado. El gate de paquete comprueba el contrato del `package.json` y rechaza un listado de artefacto sin `vocify-tap` o `shared/ui`; no sustituye abrir el DMG.
