"""Runtime feature flags (environment-driven, read per request).

``SKINMAKER_JOB_EDITOR=0`` turns off the per-skin website editor without a code
deploy: generation still works and returns skins, but no job record is created,
``/edit/{id}`` and the job APIs return 404, and the editor assets are not served.
The default is on.
"""
from __future__ import annotations

import os

JOB_EDITOR_ENV = "SKINMAKER_JOB_EDITOR"
_OFF = ("0", "false", "off", "no", "")


def job_editor_on() -> bool:
    raw = os.environ.get(JOB_EDITOR_ENV)
    if raw is None:
        return True
    return str(raw).strip().lower() not in _OFF
