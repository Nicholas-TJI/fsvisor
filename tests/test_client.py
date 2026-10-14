from __future__ import annotations

import pandas as pd
import pytest
import requests

from fsvisor import FormSiteClient


class _ListLogger:
    def __init__(self):
        self.records: list[tuple[str, str]] = []

    def info(self, msg: str):
        self.records.append(("info", msg))

    def warning(self, msg: str):
        self.records.append(("warning", msg))

    def error(self, msg: str):
        self.records.append(("error", msg))


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error", response=self)

    def json(self):
        return self._payload


@pytest.fixture
def client(monkeypatch) -> FormSiteClient:
    monkeypatch.setenv("FORMSITE_REALM_HOSTNAME", "server.formsite.com")
    monkeypatch.setenv("FORMSITE_API_KEY", "Bearer token")
    monkeypatch.setenv("FORMSITE_USER_ID", "user")
    monkeypatch.setattr("fsvisor.client.time.sleep", lambda *_a, **_k: None)
    monkeypatch.setattr("fsvisor.client.random.uniform", lambda *_a, **_k: 1.0)
    return FormSiteClient(logger=_ListLogger(), load_env=False)


def test_construct_url(client) -> None:
    assert client._construct_url("abc/results") == "https://server.formsite.com/api/v2/user/forms/abc/results"


def test_explicit_args_override_env(client) -> None:
    other = FormSiteClient(
        realm_hostname="fs22.formsite.com",
        api_key="raw-token",
        user_id="someone",
        load_env=False,
    )
    assert other._construct_url("x") == "https://fs22.formsite.com/api/v2/someone/forms/x"
    assert other.headers["Authorization"] == "Bearer raw-token"


def test_missing_credentials_raise(monkeypatch) -> None:
    monkeypatch.delenv("FORMSITE_REALM_HOSTNAME", raising=False)
    monkeypatch.delenv("FORMSITE_API_KEY", raising=False)
    monkeypatch.delenv("FORMSITE_USER_ID", raising=False)
    with pytest.raises(ValueError):
        FormSiteClient(load_env=False)


@pytest.mark.parametrize(
    "transient",
    [
        requests.exceptions.ConnectionError("dropped"),
        requests.exceptions.Timeout("slow"),
        _Response({}, status_code=429),
        _Response({}, status_code=503),
    ],
)
def test_make_request_retries_transient_errors_then_succeeds(client, transient) -> None:
    calls = {"count": 0}

    def _method(*_a, **_k):
        calls["count"] += 1
        if calls["count"] == 1:
            if isinstance(transient, Exception):
                raise transient
            return transient
        return _Response({"ok": True})

    response = client._make_request(_method, "https://example.com")
    assert response.json()["ok"] is True
    assert calls["count"] == 2
    assert any(level == "warning" for level, _ in client.logger.records)


@pytest.mark.parametrize("status_code", [400, 401, 403, 404])
def test_make_request_raises_client_errors_without_retrying(client, status_code) -> None:
    calls = {"count": 0}

    def _method(*_a, **_k):
        calls["count"] += 1
        return _Response({}, status_code=status_code)

    with pytest.raises(requests.exceptions.HTTPError) as excinfo:
        client._make_request(_method, "https://example.com")
    assert excinfo.value.response.status_code == status_code
    assert calls["count"] == 1


def test_make_request_raises_after_max_attempts(client) -> None:
    calls = {"count": 0}

    def _method(*_a, **_k):
        calls["count"] += 1
        raise requests.exceptions.ConnectionError("always failing")

    with pytest.raises(requests.exceptions.ConnectionError):
        client._make_request(_method, "https://example.com")
    assert calls["count"] == 5
    assert any(level == "error" for level, _ in client.logger.records)


def test_failed_requests_propagate_from_public_methods(client, monkeypatch) -> None:
    monkeypatch.setattr("fsvisor.client.requests.get", lambda *_a, **_k: _Response({}, status_code=401))
    with pytest.raises(requests.exceptions.HTTPError):
        client.get_form_results("form-1")
    with pytest.raises(requests.exceptions.HTTPError):
        client.get_form_metadata("form-1")
    with pytest.raises(requests.exceptions.HTTPError):
        client.get_results_dataframe("form-1", results_view=10)


def test_get_form_results_and_metadata(client, monkeypatch) -> None:
    monkeypatch.setattr(
        client,
        "_make_request",
        lambda *_a, **_k: _Response({"results": [{"id": 1}], "items": [{"id": "1", "label": "Date"}]}),
    )
    assert client.get_form_results("form-1", page=1, limit=10) == [{"id": 1}]
    assert client.get_form_metadata("form-1") == {"1": "Date"}


def test_get_results_dataframe_pagination_and_labels(client, monkeypatch) -> None:
    page_data = {
        1: [
            {
                "items": [
                    {"id": "1", "value": "2026-02-10"},
                    {"id": "2", "values": [{"value": "A"}, {"value": "B"}]},
                ]
            },
            {"items": [{"id": "1", "value": "2026-02-09"}, {"id": "2", "value": "C"}]},
        ],
        2: [],
    }

    def _fake_results(_form_id, _view, page=1, **_kwargs):
        return page_data[page]

    monkeypatch.setattr(client, "get_form_results", _fake_results)
    monkeypatch.setattr(client, "get_form_metadata", lambda *_a, **_k: {"1": "Date", "2": "Inspector"})

    df = client.get_results_dataframe(form_id="x", results_view=10, limit_per_request=2, results_labels=123)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["Date", "Inspector"]
    assert df.iloc[0]["Inspector"] == "A; B"
    assert len(df) == 2


@pytest.mark.parametrize(
    ("attr", "value"),
    [("realm_hostname", "bad-host"), ("authorization", None), ("user_id", None)],
)
def test_property_validation_errors(client, attr, value) -> None:
    with pytest.raises(ValueError):
        setattr(client, attr, value)
