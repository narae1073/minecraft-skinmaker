"""Runtime feature flags."""
import pytest

from backend.features import job_editor_on


@pytest.mark.parametrize("value", ["0", "false", "off", "no", ""])
def test_job_editor_off_values(monkeypatch, value):
    monkeypatch.setenv("SKINMAKER_JOB_EDITOR", value)
    assert job_editor_on() is False


@pytest.mark.parametrize("value", ["1", "true", "on", "yes", "ON"])
def test_job_editor_on_values(monkeypatch, value):
    monkeypatch.setenv("SKINMAKER_JOB_EDITOR", value)
    assert job_editor_on() is True


def test_job_editor_defaults_on(monkeypatch):
    monkeypatch.delenv("SKINMAKER_JOB_EDITOR", raising=False)
    assert job_editor_on() is True
