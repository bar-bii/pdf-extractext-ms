# pdf-extractext-ms

API para extraer texto de archivos PDF y persistirlo en MongoDB con deduplicación por checksum, **delegando la extracción en un microservicio dedicado**.

Es la variante de `pdf-extractext` en la que la lógica de extracción ya no vive en la app: esta API valida, calcula el SHA-256, consulta al microservicio por HTTP (`POST /extract`) y persiste el resultado. Proyecto académico de **Desarrollo de Software 2026** — UTN Facultad Regional San Rafael.

## Cómo funciona

```
cliente ──► app (:8000) ──► Traefik ──► extractor ×5   (microservicio de extracción)
                │
                └──► MongoDB
```

1. Recibe un PDF vía `multipart/form-data`.
2. Calcula el SHA-256 del PDF. Si ya existe, responde `409` **sin llamar al extractor**.
3. Envía el PDF al microservicio y obtiene el texto (`content`).
4. Persiste solo el texto y el checksum (nunca el binario) y lo devuelve.
5. Expone el CRUD de documentos persistidos.

El PDF nunca se escribe a disco en esta app.

## Arquitectura

Clean Architecture (`presentation → application ← data`):

- `application/pdf_extractor.py` — `Protocol` `PDFExtractor` y excepciones de dominio.
- `data/extractor_client.py` — `HttpPDFExtractor`, cliente `httpx` del microservicio.
- `data/` — modelos Beanie y repositorios de MongoDB.
- `presentation/main.py` — app FastAPI, wiring de dependencias y mapeo de errores.

## Requisitos

- Python 3.13+ y [uv](https://docs.astral.sh/uv/)
- Docker
- El proyecto del microservicio de extracción (`Microservicios`) clonado como carpeta hermana (`../Microservicios`), o su ruta en `EXTRACTOR_CONTEXT`.

## Arranque

Stack completo (MongoDB + app + Traefik + 5 réplicas del extractor):

```bash
docker compose up --build
```

La API queda en `http://localhost:8000` (Swagger en `/docs`). Cada réplica del extractor tiene un límite de 1 CPU y 1 GB de RAM.

Desarrollo local contra un extractor ya levantado:

```bash
uv sync
docker compose up mongodb -d
EXTRACTOR_URL=http://localhost:8080 uv run uvicorn presentation.main:app --reload
```

## Configuración

| Variable | Descripción | Default |
|---|---|---|
| `DB_URL` | Connection string de MongoDB | `mongodb://localhost:27017` |
| `DB_NAME` | Nombre de la base de datos | `pdf_extractext` |
| `EXTRACTOR_URL` | URL base del microservicio de extracción | `http://localhost:8080` |
| `EXTRACTOR_TIMEOUT_SECONDS` | Timeout de cada llamada al extractor | `30` |

## Endpoints

| Método | Path | Descripción |
|---|---|---|
| `GET` | `/health` | Chequeo de salud |
| `POST` | `/extract` | Sube un PDF, lo extrae vía microservicio y lo persiste si es único |
| `GET` | `/documents` | Lista los documentos |
| `GET` | `/documents/{id}` | Obtiene un documento |
| `PATCH` | `/documents/{id}` | Actualiza texto y/o checksum |
| `DELETE` | `/documents/{id}` | Elimina un documento |

### Errores de `POST /extract`

| Situación | Respuesta |
|---|---|
| Checksum ya existente | `409` |
| El extractor rechaza el archivo (no es PDF, muy grande, tipo inválido) | `400` / `413` / `415` con su `detail` |
| Extractor saturado, caído o con error | `503` (con `Retry-After` si el extractor lo envió) |
| Extractor demasiado lento | `504` |

No hay reintentos automáticos.

## Tests

El proyecto sigue TDD (Red → Green → Refactor).

```bash
uv run pytest
```

`tests/test_database.py` es de integración y requiere MongoDB (`docker compose up mongodb -d`).

## Licencia

MIT — ver [LICENSE](LICENSE).
