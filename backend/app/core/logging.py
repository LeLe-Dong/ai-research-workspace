import logging
import sys


def setup_logging(debug: bool = False) -> None:
    """Configure root logger + quiet down noisy libraries.

    Defaults to WARNING level — only real warnings/errors are shown.
    Pass debug=True for development (chatty SQL traces).

    Quiet loggers (always):
      - aiosqlite      (every SQL execute/close produces DEBUG spam)
      - sqlalchemy.engine
      - asyncio        (selector selection, etc.)
    """
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
        force=True,
    )
    # Quiet noisy third-party loggers regardless of debug level
    for noisy in ("aiosqlite", "sqlalchemy.engine", "asyncio", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
