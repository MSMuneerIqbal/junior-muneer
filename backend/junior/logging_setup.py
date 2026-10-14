"""One logging format for the whole backend."""

import logging


class _DropClosedConnectionNoise(logging.Filter):
    """On Windows, asyncio logs a ConnectionResetError every time a browser tab
    closes its WebSocket. It's harmless, so keep it out of the log."""

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not isinstance(exc, ConnectionResetError)


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
    asyncio_log = logging.getLogger("asyncio")
    if not any(isinstance(f, _DropClosedConnectionNoise) for f in asyncio_log.filters):
        asyncio_log.addFilter(_DropClosedConnectionNoise())
