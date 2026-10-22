"""Which client a public identity request is counted against.

Behind a proxy every request shares the proxy's address, so a shared limiter keyed on the socket
peer would become one platform-wide budget. A deployment whose edge *overwrites* a client-address
header (Vercel sets ``x-real-ip``) names it in ``TALEEM_CLIENT_IP_HEADER``; anywhere else the header
must be ignored, because a client-supplied value would buy a fresh budget per request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from taleem_core.contexts.identity.adapters.identity_api import SIGN_IN_LIMIT
from taleem_core.main import create_app
from taleem_core.platform.config import Settings

_BODY = {"email": "nobody@example.com", "passphrase": "not-the-passphrase"}


def _statuses(client: TestClient, ip: str, attempts: int) -> list[int]:
    return [
        client.post(
            "/v1/identity/guardians:signin", json=_BODY, headers={"X-Real-IP": ip}
        ).status_code
        for _ in range(attempts)
    ]


def test_a_trusted_header_separates_clients_behind_one_proxy() -> None:
    client = TestClient(
        create_app(Settings(database_url="", kdf_iterations=1_000, client_ip_header="x-real-ip"))
    )
    first = _statuses(client, "203.0.113.7", SIGN_IN_LIMIT + 1)
    assert first[-1] == 429 and 429 not in first[:-1]
    # A different real client behind the same proxy is not collateral damage.
    assert 429 not in _statuses(client, "198.51.100.9", SIGN_IN_LIMIT)


def test_the_first_hop_of_a_list_is_used() -> None:
    client = TestClient(
        create_app(
            Settings(database_url="", kdf_iterations=1_000, client_ip_header="X-Forwarded-For")
        )
    )
    statuses = [
        client.post(
            "/v1/identity/guardians:signin",
            json=_BODY,
            headers={"X-Forwarded-For": f"203.0.113.7, 10.0.0.{i}"},
        ).status_code
        for i in range(SIGN_IN_LIMIT + 1)
    ]
    assert statuses[-1] == 429


def test_without_configuration_the_header_is_ignored() -> None:
    """Rotating a spoofable header must not buy a fresh budget."""
    client = TestClient(create_app(Settings(database_url="", kdf_iterations=1_000)))
    statuses = [
        client.post(
            "/v1/identity/guardians:signin", json=_BODY, headers={"X-Real-IP": f"203.0.113.{i}"}
        ).status_code
        for i in range(SIGN_IN_LIMIT + 1)
    ]
    assert statuses[-1] == 429


@pytest.mark.parametrize(("vercel", "expected"), [("1", "x-real-ip"), ("", "")])
def test_vercel_defaults_to_its_own_client_header(
    monkeypatch: pytest.MonkeyPatch, vercel: str, expected: str
) -> None:
    monkeypatch.delenv("TALEEM_CLIENT_IP_HEADER", raising=False)
    monkeypatch.setenv("VERCEL", vercel)
    assert Settings().client_ip_header == expected
