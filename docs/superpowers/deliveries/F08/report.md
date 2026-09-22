# Informe F08

Estado: C06 empezado en `feat/vocify-v1`. No cerrado. Publicar discovery exige un borrador de texto y no marca las otras tipologías. Un member recibe 403. El estado vive en memoria del proceso (`_MOTIONS`, `_IMPORTS`), no en las tablas de `040`. Settings ya no marca «publicado» con un clic local.

## Entregado

| Pieza | Commit | Prueba |
|---|---|---|
| Una versión activa; la captura conserva la versión del inicio; entrada sin fuente no se publica | commits previos de la rama | `tests/playbooks/test_versions.py` |
| PDF sin texto no publica; el audio queda en borrador y no crea un memo | commits previos de la rama | `tests/playbooks/test_imports.py` |
| Publicar discovery deja qualification sin publicar; sin borrador es 409; member es 403 | este commit | `tests/playbooks/test_versions.py` |
| Un rechazo no cambia el borrador; el resultado de otra tipología no publica discovery | este commit | `src/lib/playbook-setup.test.ts` |

## No verificado

- Reticle no tiene sesión en este worktree, así que el aviso de Settings no se recorrió en el navegador.
- PDF y audio siguen en la API de importación; la pantalla solo guarda texto.
- Reiniciar el proceso pierde borradores y publicaciones de `_MOTIONS`.
