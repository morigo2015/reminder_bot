import asyncio
from typing import Callable, Any

BACKOFFS = [1, 3, 10]

async def with_retry(func: Callable[..., Any], *args, **kwargs):
    last_exc = None
    for attempt in range(len(BACKOFFS) + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:  # aiogram/HTTPError
            last_exc = e
            if attempt == len(BACKOFFS):
                raise
            await asyncio.sleep(BACKOFFS[attempt])
    raise last_exc
