import asyncio
from types import SimpleNamespace

import httpx
import pytest

from auditor import ai


@pytest.mark.parametrize(
    "statuses,expected_calls,success",
    [([503, 200], 2, True), ([502, 504, 200], 3, True), ([503] * 4, 4, False), ([401], 1, False)],
)
def test_transient_provider_errors_retry_with_a_bound(monkeypatch, statuses, expected_calls, success):
    requests, delays = [], []

    def respond(request):
        requests.append(request.content)
        status = statuses[len(requests) - 1]
        payload = (
            {"choices": [{"finish_reason": "stop", "message": {"content": '{"result":"ok"}'}}]}
            if status == 200
            else {"error": {"message": "Synthetic provider failure"}}
        )
        return httpx.Response(status, json=payload, headers={"retry-after": "35"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        ai.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    monkeypatch.setattr(
        ai,
        "settings",
        lambda: SimpleNamespace(
            groq_api_key="synthetic-key",
            groq_zdr_confirmed=True,
            groq_model="synthetic-model",
        ),
    )
    monkeypatch.setattr(ai, "_last_request", 0)
    monkeypatch.setattr(ai, "_lock", asyncio.Lock())

    async def pause(seconds):
        delays.append(seconds)

    monkeypatch.setattr(ai.asyncio, "sleep", pause)
    if success:
        result, _ = asyncio.run(ai.ask_json("Return JSON.", max_tokens=100))
        assert result == {"result": "ok"}
    else:
        with pytest.raises(
            ai.AIUnavailable, match="after retries" if statuses[0] == 503 else "not authorized"
        ):
            asyncio.run(ai.ask_json("Return JSON.", max_tokens=100))
    assert len(requests) == expected_calls
    assert all(body == requests[0] for body in requests)
    assert delays == [35] * (expected_calls - 1)
