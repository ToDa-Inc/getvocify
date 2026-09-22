# Informe F08

Estado: C06 empezado en `feat/vocify-v1`. No cerrado. Un borrador de texto se guarda en `playbooks` / `playbook_versions` / `playbook_imports` y publicar discovery no crea qualification. El arranque instala ese almacén. La migración `040` no está aplicada en una base compartida. Reticle no recorrió Settings.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Una versión activa; la captura conserva la versión del inicio; entrada sin fuente no se publica | commits previos de la rama | `tests/playbooks/test_versions.py` |
| PDF sin texto no publica; el audio queda en borrador y no crea un memo | commits previos de la rama | `tests/playbooks/test_imports.py` |
| Publicar discovery deja qualification sin publicar; sin borrador es 409; member es 403 | `feff559` | `tests/playbooks/test_versions.py` |
| Un rechazo no cambia el borrador; el resultado de otra tipología no publica discovery | `feff559` | `src/lib/playbook-setup.test.ts` |
| El borrador queda en Postgres; repetir el mismo import no crea otra versión; qualification no aparece | este commit | `tests/playbooks/test_versions.py` contra PostgreSQL |

## No verificado

- Reticle no tiene sesión en este worktree, así que el aviso de Settings no se recorrió en el navegador.
- PDF y audio siguen en la API de importación; la pantalla solo guarda texto.
- Sin pasar por el arranque de la API, los tests HTTP usan el almacén en memoria.
