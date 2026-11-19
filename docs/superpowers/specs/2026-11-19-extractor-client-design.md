# pdf-extractext-ms — diseño

Variante de `pdf-extractext` que **no extrae texto por sí misma**: delega la extracción en el microservicio
de extracción (`POST /extract`, ver proyecto `Microservicios`) y conserva en esta app la deduplicación por
checksum, la persistencia en MongoDB y el CRUD.

## Decisión de alcance

No se crea ningún microservicio adicional. La parte costosa en CPU (parsear el PDF) ya es el microservicio de
extracción. Lo que queda acá (SHA-256, consulta de checksum y CRUD sobre la misma base) es barato y está
acoplado a MongoDB; separarlo sumaría latencia y puntos de falla sin ganar escalabilidad (YAGNI).

## Arquitectura

Se mantiene `presentation → application ← data`.

- `application/pdf_extractor.py`: `Protocol` asíncrono `PDFExtractor` y excepciones de dominio
  (`ExtractorRejectedError`, `ExtractorUnavailableError`, `ExtractorTimeoutError`).
- `data/extractor_client.py`: `HttpPDFExtractor`, implementa el `Protocol` con `httpx.AsyncClient`
  (`POST {EXTRACTOR_URL}/extract`, multipart, `Content-Type: application/pdf`) y devuelve el campo `content`.
- `data/config.py`: `ExtractorSettings` (`EXTRACTOR_URL`, `EXTRACTOR_TIMEOUT_SECONDS`).
- `presentation/main.py`: crea el cliente HTTP en el `lifespan` y lo inyecta con `Depends`.

## Flujo de `POST /extract`

1. Calcula SHA-256 del PDF crudo. Si ya existe, responde `409` **sin llamar al extractor**.
2. Llama al extractor y obtiene `content`.
3. Persiste `content` + checksum y responde `{text, checksum}` (contrato idéntico a `pdf-extractext`).

`page_count` de la respuesta del extractor se ignora (YAGNI).

## Errores del extractor

| Extractor | Esta API |
|---|---|
| 400 / 413 / 415 | mismo código y `detail` |
| 429 / 503 / cualquier otro error | 503 (con `Retry-After` si el extractor lo envió) |
| sin conexión | 503 |
| timeout | 504 |

Sin reintentos.

## Despliegue

`docker-compose.yml`: MongoDB, la app, Traefik y 5 réplicas del extractor (1 CPU / 1 GB cada una), construido
desde `../Microservicios`. La app lo alcanza por `http://traefik` dentro de la red interna.

## Tests (TDD)

- Cliente HTTP con `httpx.MockTransport`.
- API con el extractor reemplazado vía `dependency_overrides` (409 sin llamar al extractor, mapeo de errores).
- Tests de CRUD existentes sin cambios.
