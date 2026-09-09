"""Logging configuration and utilities for Convergence Factory."""
from __future__ import annotations

import logging
import os
import sys
from typing import Optional

LOGGER = logging.getLogger("convergence_factory")


def setup_logger(verbose: bool = False, level: Optional[int] = None) -> logging.Logger:
    """Configures console logging with clean timestamped formatting.

    Respects CONVERGENCE_LOG_LEVEL environment variable if set (DEBUG, INFO, WARNING, ERROR).
    """
    env_level = os.environ.get("CONVERGENCE_LOG_LEVEL", "").upper()
    if env_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        log_level = getattr(logging, env_level)
    elif level is not None:
        log_level = level
    else:
        log_level = logging.DEBUG if verbose else logging.INFO

    LOGGER.setLevel(log_level)

    if not LOGGER.handlers:
        handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        LOGGER.addHandler(handler)
    else:
        LOGGER.setLevel(log_level)
        for h in LOGGER.handlers:
            h.setLevel(log_level)

    return LOGGER
