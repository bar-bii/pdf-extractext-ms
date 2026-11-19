from pydantic_settings import BaseSettings


# Única responsabilidad: exponer los settings de conexión a la DB (SOLID: SRP).
# Se apoya en pydantic-settings para leer DB_URL/DB_NAME del entorno en vez de
# parsear variables de entorno a mano (KISS).
class DatabaseSettings(BaseSettings):
    url: str = "mongodb://localhost:27017"
    name: str = "pdf_extractext"

    model_config = {"env_prefix": "DB_"}


# Settings del microservicio de extracción, leídos de EXTRACTOR_URL y
# EXTRACTOR_TIMEOUT_SECONDS (12-factor: config por entorno).
class ExtractorSettings(BaseSettings):
    url: str = "http://localhost:8080"
    timeout_seconds: float = 30

    model_config = {"env_prefix": "EXTRACTOR_"}
