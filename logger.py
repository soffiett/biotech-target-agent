"""
Centralized logging configuration.

Usage in any module:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("message")
    log.warning("message")
    log.error("message", exc_info=True)  # includes stack trace

On ECS Fargate, CloudWatch captures all stderr output. The console handler is
set to INFO in that environment so performance-relevant log lines (node timing,
tool call counts, findings counts) appear in CloudWatch alongside warnings and
errors. Locally it defaults to WARNING to keep the terminal clean.

Set LOG_LEVEL=INFO in the container environment (already done in deploy.sh) to
enable this without changing code between environments.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "app.log"

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_configured = False

# On Fargate, LOG_LEVEL=INFO is set via ECS task definition environment variable.
# Locally, falls back to WARNING to keep the terminal clean.
_CONSOLE_LEVEL = getattr(logging, os.environ.get("LOG_LEVEL", "WARNING").upper(), logging.WARNING)


def _configure() -> None:
    global _configured
    if _configured:
        return

    LOG_DIR.mkdir(exist_ok=True)

    root = logging.getLogger("biotech")
    root.setLevel(logging.DEBUG)

    # File handler — DEBUG and above, rotates at 5MB, keeps 3 backups
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    # Console handler — level controlled by LOG_LEVEL env var.
    # INFO on Fargate (CloudWatch performance monitoring); WARNING locally.
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(_CONSOLE_LEVEL)
    ch.setFormatter(logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT))

    root.addHandler(fh)
    root.addHandler(ch)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger under the 'biotech' root logger."""
    _configure()
    short_name = name.replace("graph.nodes.", "nodes.").replace("tools.", "tools.")
    return logging.getLogger(f"biotech.{short_name}")
