import asyncio

import pytest

from auditor.security import RequestBodyLimit


def exchange(chunks, headers=(), limit=8):
    responses = []
    delivered = []
    messages = [
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    ]

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        responses.append(message)

    async def app(scope, receive, send):
        delivered.append(await receive())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    asyncio.run(RequestBodyLimit(app, limit)({"type": "http", "headers": headers}, receive, send))
    return responses, delivered


@pytest.mark.parametrize("headers", [[], [(b"content-length", b"1")]])
def test_chunked_or_understated_body_cannot_reach_parser_above_limit(headers):
    responses, delivered = exchange([b"1234", b"5678", b"9"], headers)
    assert responses[0]["status"] == 413
    assert delivered == []


def test_limit_allows_exact_size_and_preserves_body():
    responses, delivered = exchange([b"1234", b"5678"])
    assert responses[0]["status"] == 200
    assert delivered == [{"type": "http.request", "body": b"12345678", "more_body": False}]


@pytest.mark.parametrize(
    "headers,status",
    [
        ([(b"content-length", b"9")], 413),
        ([(b"content-length", b"-1")], 400),
        ([(b"content-length", b"9" * 5000)], 400),
        ([(b"content-length", b"1"), (b"content-length", b"2")], 400),
    ],
)
def test_reject_invalid_or_oversized_declared_length(headers, status):
    responses, delivered = exchange([], headers)
    assert responses[0]["status"] == status
    assert delivered == []


def test_workbook_xml_entities_are_rejected():
    import io
    import zipfile

    from defusedxml.common import EntitiesForbidden

    from auditor.parsing import workbook_tables

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<!DOCTYPE Types [<!ENTITY repeat "untrusted">]>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '&repeat;</Types>',
        )
    with pytest.raises(ValueError) as error:
        workbook_tables(buffer.getvalue(), ".xlsx")
    assert isinstance(error.value.__cause__, EntitiesForbidden)
