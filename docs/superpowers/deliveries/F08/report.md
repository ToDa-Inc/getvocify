# Informe F08

Estado: C06 empezado en `feat/vocify-v1`. No cerrado. Un texto contradictorio se queda en borrador, se puede reabrir por su id y no sustituye la versión activa. La migración `040` no está aplicada en una base compartida. Reticle no recorrió Settings.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Una versión activa; la captura conserva la versión del inicio; entrada sin fuente no se publica | commits previos de la rama | `tests/playbooks/test_versions.py` |
| PDF sin texto no publica; el audio queda en borrador y no crea un memo | commits previos de la rama | `tests/playbooks/test_imports.py` |
| Publicar discovery deja qualification sin publicar; sin borrador es 409; member es 403 | `feff559` | `tests/playbooks/test_versions.py` |
| Un rechazo no cambia el borrador; el resultado de otra tipología no publica discovery | `feff559` | `src/lib/playbook-setup.test.ts` |
| El borrador queda en Postgres; repetir el mismo import no crea otra versión; qualification no aparece | `0367e6f` | `tests/playbooks/test_versions.py` contra PostgreSQL |
| La versión guarda `source_ref`; añadir `renewal` no la publica; un PDF sin texto no sustituye lo publicado | `29d81a0` | `tests/playbooks/test_versions.py`, `src/lib/playbook-setup.test.ts` |
| pypdf extrae el texto; un PDF con contraseña no sustituye la versión activa; el audio usa STT y no crea un memo | `48df491` | `tests/playbooks/test_imports.py` |
| Un borrador con «nunca/siempre» no se publica y se puede reabrir por el id de importación | este commit | `tests/playbooks/test_imports.py`, `tests/playbooks/test_versions.py` |

## No verificado

- Reticle no tiene sesión en este worktree, así que el aviso de Settings no se recorrió en el navegador.
- La pantalla envía el PDF en base64 y el servidor lo lee con pypdf. No hay OCR.
- Sin pasar por el arranque de la API, los tests HTTP usan el almacén en memoria. El audio de producción llama a `transcribe_bytes` y no crea un memo.
