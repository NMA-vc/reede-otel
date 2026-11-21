import os
import reede_otel


def fresh(monkeypatch):
    for k in ("REEDE_OTLP_ENDPOINT", "REEDE_TOKEN", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS"):
        monkeypatch.delenv(k, raising=False)


def test_default_is_local_reede_without_auth(monkeypatch):
    fresh(monkeypatch)
    assert reede_otel.configure() == "http://127.0.0.1:4318"
    assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://127.0.0.1:4318"
    assert "authorization" not in os.environ["OTEL_EXPORTER_OTLP_HEADERS"]


def test_endpoint_and_token(monkeypatch):
    fresh(monkeypatch)
    reede_otel.configure("https://reede.example/", token="t0k")
    assert os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] == "https://reede.example"
    assert os.environ["OTEL_EXPORTER_OTLP_HEADERS"] == "authorization=Bearer t0k"


def test_env_fallback(monkeypatch):
    fresh(monkeypatch)
    monkeypatch.setenv("REEDE_OTLP_ENDPOINT", "http://10.0.0.5:4318")
    assert reede_otel.configure() == "http://10.0.0.5:4318"
