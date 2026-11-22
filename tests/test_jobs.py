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


def _record(token="0123456789ab", owner="ownerhash", seed=12345):
    observed = Q._observed()
    attrs = A.validate(dict(Q._attrs("long", "long_straight", "none").values, top_garment="tee"))
    cand = SimpleNamespace(index=1, varied="", noise_seed=seed, attributes=attrs)
    return jobs.create_record(token, owner, observed, [cand], model="classic", noise_level=1.0,
                              degrade=()), observed, attrs


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


def test_set_attributes_merges_and_keeps_other_overrides():
    record, _observed, _attrs = _record()
    jobs.set_attributes(record, {"top_garment": "hoodie", "sleeve_len": "long"})
    assert record["attr_overrides"] == {"top_garment": "hoodie", "sleeve_len": "long"}
    jobs.set_headwear(record, "cap", "#ff0000")
    assert record["attr_overrides"]["top_garment"] == "hoodie"
    assert record["attr_overrides"]["headwear"] == "cap"
    assert record["hat_color"] == "#ff0000"
    assert "headwear.cap" in record["overlay"]
    attrs = jobs.candidate_attributes(record, 1)
    assert attrs.get("top_garment") == "hoodie"
    assert attrs.get("headwear") == "cap"


def test_set_attributes_rejects_unknown_keys_values_and_too_many_changes():
    record, _observed, _attrs = _record()
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {"pattern": "check"})   # not an editable field
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {"top_garment": "spacesuit"})
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {"headwear": "fedora"})
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {"top_garment": "hoodie"}, hat_color="red")
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {f"top_garment": "tee"} | {f"k{i}": "x" for i in range(8)})
    assert not record.get("attr_overrides")


def test_reset_attributes_restores_the_photo_values():
    record, _observed, _attrs = _record()
    base_top = jobs.candidate_attributes(record, 1).get("top_garment")
    jobs.set_attributes(record, {"top_garment": "hoodie"})
    jobs.set_headwear(record, "beanie", "#123456")
    jobs.reset_attributes(record)
    assert "attr_overrides" not in record
    assert "hat_color" not in record
    assert jobs.candidate_attributes(record, 1).get("top_garment") == base_top


def test_hat_on_top_is_set_only_when_a_hat_was_chosen(monkeypatch):
    from PIL import Image
    from types import SimpleNamespace
    seen = []

    def fake_render(observed, attrs, degrade, model, **kwargs):
        seen.append(kwargs.get("hat_on_top"))
        return SimpleNamespace(image=Image.new("RGBA", (64, 64)))

    monkeypatch.setattr(jobs.R, "render", fake_render)
    monkeypatch.setattr("skinmaker.validate.validate_image", lambda image, model: [])

    record, _observed, _attrs = _record()
    jobs.render_candidate(record, 1)
    jobs.set_attributes(record, {"top_garment": "hoodie"})
    jobs.render_candidate(record, 1)
    jobs.set_headwear(record, "cap")
    jobs.render_candidate(record, 1)
    jobs.set_headwear(record, "none")
    jobs.render_candidate(record, 1)
    # render_candidate renders the skin and the flat variant each time.
    assert seen == [False, False, False, False, True, True, False, False]


def _add_second_candidate(record):
    import copy
    second = copy.deepcopy(record["candidates"][0])
    second["index"] = 2
    second["seed"] = int(second["seed"]) + 1
    record["candidates"].append(second)
    return record


def test_overlays_are_per_candidate_and_history_is_capped():
    record, _observed, _attrs = _record()
    _add_second_candidate(record)
    entry = {"L1": {"head.front": [[1] * 8 for _ in range(8)]}, "L2": {}}
    jobs.save_candidate_overlay(record, 1, {"top_garment.tee": entry})
    jobs.save_candidate_overlay(record, 2, {"bottom_garment.jeans": entry})
    assert jobs.effective_overlay(record, 1) == {"top_garment.tee": entry}
    assert jobs.effective_overlay(record, 2) == {"bottom_garment.jeans": entry}
    assert [h["revision"] for h in jobs.overlay_history(record, 1)] == [1]
    assert [h["revision"] for h in jobs.overlay_history(record, 2)] == [2]
    for _ in range(12):
        jobs.save_candidate_overlay(record, 1, {"top_garment.tee": entry})
    assert len(jobs.overlay_history(record, 1)) == jobs.OVERLAY_HISTORY_MAX


def test_shared_overlay_merges_with_candidate_overlay():
    record, _observed, _attrs = _record()
    record["overlay"] = {"headwear.cap": {"L1": {"head.top": [[1] * 8]}, "L2": {}}}
    jobs.save_candidate_overlay(record, 1, {"top_garment.tee": {"L1": {}, "L2": {}}})
    merged = jobs.effective_overlay(record, 1)
    assert set(merged) == {"headwear.cap", "top_garment.tee"}


def test_restore_brings_back_an_older_overlay_as_a_new_revision():
    record, _observed, _attrs = _record()
    entry = {"L1": {"head.front": [[1] * 8 for _ in range(8)]}, "L2": {}}
    jobs.save_candidate_overlay(record, 1, {"top_garment.tee": entry})
    jobs.save_candidate_overlay(record, 1, {})
    revision = jobs.restore_candidate_overlay(record, 1, 1)
    assert revision == 3
    assert jobs.effective_overlay(record, 1) == {"top_garment.tee": entry}
    assert [h["revision"] for h in jobs.overlay_history(record, 1)] == [3, 2, 1]
    with pytest.raises(KeyError):
        jobs.restore_candidate_overlay(record, 1, 99)


def test_hair_style_and_length_are_editable_and_resettable():
    record, _observed, _attrs = _record()
    base = jobs.candidate_attributes(record, 1)
    jobs.set_attributes(record, {"hair_style": "bob", "hair_length": "medium"})
    attrs = jobs.candidate_attributes(record, 1)
    assert attrs.get("hair_style") == "bob" and attrs.get("hair_length") == "medium"
    # Hair masks are seeded for every value, so an attribute change adds no fake overrides.
    assert jobs.override_names(record, 1) == []
    with pytest.raises(ValueError):
        jobs.set_attributes(record, {"hair_length": "floor"})
    jobs.reset_attributes(record)
    restored = jobs.candidate_attributes(record, 1)
    assert restored.get("hair_style") == base.get("hair_style")
    assert restored.get("hair_length") == base.get("hair_length")


def test_extra_attributes_are_editable_and_photo_values_stay_separate():
    record, _observed, _attrs = _record()
    base = jobs.photo_attributes(record, 1)
    jobs.set_attributes(record, {"inner_top": "shirt", "neckwear": "tie", "beard": "full",
                                 "hood": "up", "closure_type": "open", "collar_type": "v_neck",
                                 "pocket_type": "patch", "hood_fit": "shallow"})
    attrs = jobs.candidate_attributes(record, 1)
    assert attrs.get("inner_top") == "shirt"
    assert attrs.get("neckwear") == "tie"
    assert attrs.get("beard") == "full"
    assert attrs.get("hood") == "up"
    photo = jobs.photo_attributes(record, 1)
    assert photo.get("inner_top") == base.get("inner_top")
    assert photo.get("neckwear") == base.get("neckwear")
    assert photo.get("beard") == base.get("beard")
    assert photo.get("hood") == base.get("hood")


def test_baseline_masks_stay_cached_across_attribute_changes_and_preview_skips_flat(monkeypatch):
    record, _observed, _attrs = _record()
    jobs._BASELINE_CACHE.clear()
    first = jobs.baseline_masks(record, 1)

    def fail_if_reseeded():
        raise AssertionError("seed_masks should not run when attributes change")

    monkeypatch.setattr(jobs.AS, "seed_masks", fail_if_reseeded)
    jobs.set_attributes(record, {"top_garment": "dress", "bottom_garment": "skirt"})
    second = jobs.baseline_masks(record, 1)
    assert second is first
    assert jobs.override_names(record, 1) == []

    # preview_png(None) renders directly from the saved overlay and skips the flat pass.
    fast_png, _ = jobs.preview_png(record, 1, None)
    full_png, _ = jobs.preview_png(record, 1, jobs.effective_masks(record, 1))
    assert fast_png == full_png


def test_reset_attributes_can_reset_one_key_without_touching_the_rest():
    record, _observed, _attrs = _record()
    jobs.set_attributes(record, {"top_garment": "dress", "hair_style": "bun"})
    jobs.set_headwear(record, "cap", "#ff0000")
    jobs.reset_attributes(record, ["top_garment"])
    assert "top_garment" not in record["attr_overrides"]
    assert record["attr_overrides"]["hair_style"] == "bun"
    assert record["attr_overrides"]["headwear"] == "cap"
    assert record["hat_color"] == "#ff0000"
    jobs.reset_attributes(record, ["headwear"])
    assert "headwear" not in record["attr_overrides"]
    assert "hat_color" not in record
    assert record["attr_overrides"]["hair_style"] == "bun"
    with pytest.raises(ValueError):
        jobs.reset_attributes(record, ["pattern"])
