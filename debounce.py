import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)
DEBOUNCE_SECONDS = 10

_buffers: dict[str, list[str]] = {}
_tasks: dict[str, asyncio.Task] = {}


async def add_message(
    wa_id: str,
    text: str,
    callback: Callable[[str, str], Awaitable[None]],
):
    if wa_id not in _buffers:
        _buffers[wa_id] = []
    _buffers[wa_id].append(text)

    if wa_id in _tasks and not _tasks[wa_id].done():
        _tasks[wa_id].cancel()

    _tasks[wa_id] = asyncio.create_task(_fire(wa_id, callback))
    logger.info(f"Debounce timer reset for {wa_id} ({len(_buffers[wa_id])} message(s) buffered)")


async def _fire(wa_id: str, callback: Callable[[str, str], Awaitable[None]]):
    try:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        messages = _buffers.pop(wa_id, [])
        _tasks.pop(wa_id, None)
        if messages:
            combined = "\n".join(messages)
            logger.info(f"Debounce fired for {wa_id}: combining {len(messages)} message(s)")
            await callback(wa_id, combined)
    except asyncio.CancelledError:
        pass
