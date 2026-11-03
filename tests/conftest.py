"""Test fixture: the production attribute-mask asset is user-owned.

Shape tests must not silently change when the user promotes new masks from the
editor. Keep the legacy head masks (hood/headwear/hood_fit) for the renderer
tests; new-key mask behavior is covered by explicit ``mask_override`` tests.
The promoted production asset is still exercised by production_status tests.
"""
from __future__ import annotations

import pytest

from skinmaker import attribute_masks as AM
from backend import app as backend_app

_REAL_LOAD_MASKS = AM.load_masks
_HEAD_PREFIXES = ("hood.", "headwear.", "hood_fit.")


@pytest.fixture(autouse=True)
def _disable_rate_limit(monkeypatch):
    # The full suite issues >6 generate requests within a minute; the public
    # 6/min guard is production behavior, not a test invariant.
    monkeypatch.setattr(backend_app._rate_limiter, "limit", 0)


@pytest.fixture(autouse=True)
def _isolate_production_attribute_masks(monkeypatch):
    def _load(path=None):
        masks = _REAL_LOAD_MASKS(path)
        return {k: v for k, v in masks.items() if k.startswith(_HEAD_PREFIXES)}

    monkeypatch.setattr(AM, "load_masks", _load)
