from data.config import ExtractorSettings


def test_defaults_point_to_local_extractor(monkeypatch):
    monkeypatch.delenv("EXTRACTOR_URL", raising=False)
    monkeypatch.delenv("EXTRACTOR_TIMEOUT_SECONDS", raising=False)

    settings = ExtractorSettings()

    assert settings.url == "http://localhost:8080"
    assert settings.timeout_seconds == 30


def test_reads_values_from_environment(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_URL", "http://traefik")
    monkeypatch.setenv("EXTRACTOR_TIMEOUT_SECONDS", "5")

    settings = ExtractorSettings()

    assert settings.url == "http://traefik"
    assert settings.timeout_seconds == 5
