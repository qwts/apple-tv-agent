"""Cancellable native lock acquisition; never unlink an active lock file."""

import asyncio
from contextlib import asynccontextmanager

from filelock import FileLock, Timeout

from apple_tv_agent.errors import AgentError, ErrorCode


@asynccontextmanager
async def device_lock(directory, key, timeout=5):
    lock = FileLock(str(directory / (key + ".lock")))
    acquired = False
    try:
        directory.mkdir(parents=True, exist_ok=True)
        deadline = asyncio.get_running_loop().time() + timeout
        while not acquired:
            try:
                lock.acquire(timeout=0)
                acquired = True
            except Timeout:
                if asyncio.get_running_loop().time() >= deadline:
                    raise AgentError(ErrorCode.DEVICE_BUSY) from None
                await asyncio.sleep(0.05)
        yield
    except TimeoutError:
        raise
    except OSError:
        raise AgentError(ErrorCode.CONFIG_ERROR, details={"reason": "device_lock_io"}) from None
    finally:
        if acquired:
            lock.release()
