"""Hidden cancellable terminal input, without getpass fallback or worker threads."""

import asyncio
import os
import sys
from contextlib import contextmanager

from apple_tv_agent.errors import AgentError, ErrorCode


@contextmanager
def terminal_reader(stream=None):
    """Nonblocking hidden PIN input, so cancellation leaves no blocked thread."""
    stream = sys.stdin if stream is None else stream
    if not stream.isatty():
        raise AgentError(ErrorCode.INTERACTIVE_REQUIRED)
    if os.name == "nt":
        import msvcrt

        def read():
            return msvcrt.getwch() if msvcrt.kbhit() else ""

        yield read
    else:
        import select
        import termios

        fd = stream.fileno()
        original = termios.tcgetattr(fd)
        hidden = termios.tcgetattr(fd)
        hidden[3] &= ~(termios.ECHO | termios.ICANON)
        termios.tcsetattr(fd, termios.TCSAFLUSH, hidden)
        try:

            def read():
                if not select.select([fd], [], [], 0)[0]:
                    return ""
                value = os.read(fd, 1)
                if not value:
                    raise AgentError(ErrorCode.AUTH_FAILED, details={"reason": "input_closed"})
                return value.decode("ascii", errors="ignore")

            yield read
        finally:
            termios.tcsetattr(fd, termios.TCSAFLUSH, original)


async def read_pin(timeout=120, *, stream=None):
    print(
        "Enter the PIN displayed on the selected TV (hidden): ", end="", file=sys.stderr, flush=True
    )
    try:
        with terminal_reader(stream) as read:
            async with asyncio.timeout(timeout):
                pin = ""
                extended = False
                while True:
                    char = read()
                    if extended and char:
                        extended = False
                    elif char in ("\x00", "\xe0"):
                        extended = True
                    elif char in ("\r", "\n"):
                        if len(pin) != 4:
                            raise AgentError(
                                ErrorCode.AUTH_FAILED, details={"reason": "invalid_pin"}
                            )
                        return pin
                    elif char in ("\x03", "\x04", "\x1a"):
                        raise AgentError(ErrorCode.AUTH_FAILED, details={"reason": "canceled"})
                    elif char in ("\x08", "\x7f"):
                        pin = pin[:-1]
                    elif char and char in "0123456789":
                        pin += char
                        if len(pin) > 4:
                            raise AgentError(
                                ErrorCode.AUTH_FAILED, details={"reason": "invalid_pin"}
                            )
                    await asyncio.sleep(0.02)
    finally:
        print(file=sys.stderr)
