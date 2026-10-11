"""Karaoke Dashboard application package.

__version__ is the build version: the container image's GHCR version tag
(e.g. 2026.10.11-42, or 1.2.0 for a v1.2.0 git tag), baked in at build time
as APP_VERSION by .github/workflows/docker-publish.yml. A run outside such
an image (local development, tests) reports "dev".
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def build_version(environ: Mapping[str, str] = os.environ) -> str:
    return environ.get("APP_VERSION", "").strip() or "dev"


__version__ = build_version()
