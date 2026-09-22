# Informe F08

Estado: C06 empezado en `feat/vocify-v1`. No cerrado. Una tipología nueva se guarda sin publicar, y el borrador lleva `source_ref`. La migración `040` no está aplicada en una base compartida. Reticle no recorrió Settings.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Una versión activa; la captura conserva la versión del inicio; entrada sin fuente no se publica | commits previos de la rama | `tests/playbooks/test_versions.py` |
| PDF sin texto no publica; el audio queda en borrador y no crea un memo | commits previos de la rama | `tests/playbooks/test_imports.py` |
| Publicar discovery deja qualification sin publicar; sin borrador es 409; member es 403 | `feff559` | `tests/playbooks/test_versions.py` |
| Un rechazo no cambia el borrador; el resultado de otra tipología no publica discovery | `feff559` | `src/lib/playbook-setup.test.ts` |
| El borrador queda en Postgres; repetir el mismo import no crea otra versión; qualification no aparece | `0367e6f` | `tests/playbooks/test_versions.py` contra PostgreSQL |
| La versión guarda `source_ref`; añadir `renewal` no la publica; un PDF sin texto no sustituye lo publicado | este commit | `tests/playbooks/test_versions.py`, `src/lib/playbook-setup.test.ts` |

## No verificado

- Reticle no tiene sesión en este worktree, así que el aviso de Settings no se recorrió en el navegador.
- La pantalla puede importar un PDF leído como texto; no hay extracción con `pypdf` en el navegador.
- Sin pasar por el arranque de la API, los tests HTTP usan el almacén en memoria.
