"""Per-skin jobs: re-render equivalence, overlay effect, owner check, validation."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend import jobs  # noqa: E402

from skinmaker import attributes as A  # noqa: E402
from skinmaker import attribute_masks as AM  # noqa: E402
from skinmaker import production_qa as Q  # noqa: E402
from skinmaker import render as R  # noqa: E402


@pytest.fixture(autouse=True)
def _private_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "PRIVATE_DIR", tmp_path)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "INPUTS_DIR", tmp_path / "inputs")


def _record(token="0123456789ab", owner="ownerhash", seed=12345):
    observed = Q._observed()
    attrs = A.validate(dict(Q._attrs("long", "long_straight", "none").values, top_garment="tee"))
    cand = SimpleNamespace(index=1, varied="", noise_seed=seed, attributes=attrs)
    return jobs.create_record(token, owner, observed, [cand], model="classic", noise_level=1.0,
                              degrade=(), input_name="x.jpg"), observed, attrs


def test_rerender_with_empty_overlay_matches_the_original_render():
    record, observed, attrs = _record()
    original = R.render(observed, attrs, (), "classic", noise_seed=12345, noise_level=1.0)
    image, _flat, _problems = jobs.render_candidate(record, 1)
    assert image.tobytes() == original.image.tobytes()


def test_overlay_changes_only_the_job_render():
    record, _observed, _attrs = _record()
    shared_before = AM.load_masks()
    before, _f, _p = jobs.render_candidate(record, 1)
    overlay = {"top_garment.tee": {"L1": {"body.front": [[0] * 8 for _ in range(12)]}, "L2": {}}}
    record["overlay"] = overlay
    after, _f2, _p2 = jobs.render_candidate(record, 1)
    assert before.tobytes() != after.tobytes()
    assert AM.load_masks() == shared_before


def test_overlay_validation_rejects_bad_grids_and_unknown_keys():
    assert jobs.validate_overlay({"top_garment.tee": {"L1": {"body.front": [[2]]}, "L2": {}}})
    assert jobs.validate_overlay({"not_a_key": {"L1": {}, "L2": {}}})
    assert jobs.validate_overlay({"top_garment.tee": {"L1": {"body.front": [[1, 0]]}, "L2": {}}}) == []
    assert jobs.validate_overlay("nope")
    assert jobs.validate_overlay({"top_garment.tee": {"L1": {"body.front": [[1] * 512] * 512}}})


def test_owner_check_uses_the_cookie_secret_hash():
    from types import SimpleNamespace as NS
    secret = jobs.new_owner_secret()
    record = {"owner_hash": jobs.owner_hash(secret)}
    mine = NS(cookies={jobs.OWNER_COOKIE: secret})
    other = NS(cookies={jobs.OWNER_COOKIE: jobs.new_owner_secret()})
    assert jobs.is_owner(record, mine)
    assert not jobs.is_owner(record, other)
    assert not jobs.is_owner(record, NS(cookies={}))
    assert not jobs.is_owner({"owner_hash": None}, mine)


def test_records_are_private_and_not_under_static():
    record, _o, _a = _record()
    path = jobs.JOBS_DIR / f"{record['id']}.json"
    assert path.exists()
    assert jobs.load_record(record["id"])["owner_hash"] == "ownerhash"
    assert jobs.load_record("../etc") is None
