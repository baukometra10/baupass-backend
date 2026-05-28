"""SSE streaming helpers for AI responses."""
from __future__ import annotations

import json
from typing import Any, Generator, Iterable


def sse_event(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def chunk_text_stream(text: str, *, chunk_size: int = 48) -> Generator[str, None, None]:
    text = text or ""
    if not text:
        yield sse_event({"type": "chunk", "text": ""})
        return
    for i in range(0, len(text), chunk_size):
        yield sse_event({"type": "chunk", "text": text[i : i + chunk_size]})


def stream_agent_events(event_iter) -> Iterable[str]:
    """Yield SSE from agent stream event dicts."""
    for ev in event_iter:
        yield sse_event(ev)
        if ev.get("type") == "done":
            break


def stream_agent_result(result: dict[str, Any]) -> Iterable[str]:
    yield sse_event({"type": "start", "agentId": result.get("agentId")})
    if result.get("error"):
        yield sse_event({"type": "error", "hint": result.get("hint"), "error": result.get("error")})
        yield sse_event({"type": "done", "ok": False})
        return
    answer = result.get("answer") or ""
    for ev in chunk_text_stream(answer):
        yield ev
    yield sse_event(
        {
            "type": "done",
            "ok": True,
            "sources": result.get("sources"),
            "toolsUsed": result.get("toolsUsed"),
            "suggestedActions": result.get("suggestedActions"),
            "ragChunks": result.get("ragChunks"),
        }
    )


def iter_openai_stream(messages: list[dict], *, tools: list | None = None) -> Generator[str, None, None]:
    """Yield SSE events from OpenAI streaming API (chat without tool loop)."""
    from .assistant import _openai_stream_request

    yield sse_event({"type": "start"})
    full = []
    try:
        for delta in _openai_stream_request(messages, tools=tools):
            if delta:
                full.append(delta)
                yield sse_event({"type": "chunk", "text": delta})
        yield sse_event({"type": "done", "ok": True, "answer": "".join(full)})
    except Exception as exc:
        yield sse_event({"type": "error", "hint": str(exc)[:500]})
        yield sse_event({"type": "done", "ok": False})
