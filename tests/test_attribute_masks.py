"""General attribute-mask schema, migration and gate-facing helpers."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from skinmaker import attribute_masks as AM
from skinmaker import hood_masks as HM


def test_asset_is_valid_and_has_migrated_hood():
    data = AM.load_asset()
    assert AM.validate_asset(data) == []
    masks = AM.load_masks()
    for kind in ("up", "down"):
        assert f"hood.{kind}" in masks
        grid = AM.get_mask(masks, "hood", kind, "L1", "head", "front")
        assert len(grid) == 8 and all(len(row) == 8 for row in grid)


def test_legacy_hood_asset_converts_to_general_keys():
    masks = AM.load_masks(Path("assets/hood_masks.json"))
    assert set(masks) == {"hood.up", "hood.down"}
    assert AM.legacy_hood_masks(masks).keys() == {"up", "down"}


def test_hood_loader_reads_the_general_asset():
    loaded = HM.load_hood_masks()
    assert loaded is not None
    assert set(loaded) <= {"up", "down"}
    assert "L1" in loaded["up"] and "head.front" in loaded["up"]["L1"]


def test_validate_rejects_unknown_key_layer_and_grid():
    assert AM.validate_asset({"masks": {"bogus": {}}}) == ["invalid key: 'bogus'"]
    assert AM.validate_asset({"masks": {"hood.up": {"L9": {}}}}) == ["hood.up: invalid layer 'L9'"]
    assert AM.validate_asset({"masks": {"hood.up": {"L1": {"head.front": [[2]]}}}})
    assert AM.validate_asset({"masks": {"hood.up": {"L1": {"head.front": []}}}})


def test_medium_length_seed_uses_a_draping_style():
    """A hair_length seed is capped by its length, so the seed style must drape.

    `medium` used to be seeded with `bob` (0 torso rows), which stored an
    all-zero body mask. Style ∩ length is ANDed, so that mask erased the drape
    of every long style at medium: 0 torso rows instead of 2.
    """
    from skinmaker import attribute_seeds as AS
    from skinmaker import hairstencil as HS

    for length in ("medium", "long", "very_long"):
        style = AS.LENGTH_STYLE[length]
        front, back = HS.style_drape(style, length)
        assert min(front, back) > 0, f"{length} seeded with a no-drape style {style}"


def test_medium_length_keeps_the_procedural_body_drape():
    """long_straight + medium renders its 2 torso rows with hair masks applied."""
    from skinmaker import attributes as A
    from skinmaker import attribute_seeds as AS
    from skinmaker import production_qa as Q
    from skinmaker import render as R
    from skinmaker.canvas import rgba, shade

    base = {
        "top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
        "sleeve_len": "short", "hair_bbox": [200, 50, 800, 600],
    }
    observed = Q._observed()
    attrs = A.validate(dict(base, hair_style="long_straight", hair_length="medium"))
    with AS.using(AS.fixture_context()):
        seeds = AS.seed_masks()
    hair = {k: v for k, v in seeds.items() if k.startswith("hair_")}

    def body_rows(canvas):
        ref = shade(rgba(observed.hair.hex), R.FACE_SHADE["front"])[:3]
        rows = 0
        for v in range(12):
            if any(max(abs(a - b) for a, b in zip(canvas.get("body", "front", u, v)[:3], ref)) <= 45
                   for u in range(8)):
                rows = v + 1
        return rows

    assert body_rows(R.render(observed, attrs, (), mask_override={})) == 2
    assert body_rows(R.render(observed, attrs, (), mask_override=hair)) == 2


def test_hair_masks_never_change_the_procedural_drape_depth():
    """Every style x length renders the same torso depth with and without masks."""
    from skinmaker import attributes as A
    from skinmaker import attribute_seeds as AS
    from skinmaker import production_qa as Q
    from skinmaker import render as R
    from skinmaker.canvas import rgba, shade

    base = {
        "top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
        "sleeve_len": "short", "hair_bbox": [200, 50, 800, 600],
    }
    observed = Q._observed()
    with AS.using(AS.fixture_context()):
        seeds = AS.seed_masks()
    hair = {k: v for k, v in seeds.items() if k.startswith("hair_")}

    def body_rows(canvas):
        ref = shade(rgba(observed.hair.hex), R.FACE_SHADE["front"])[:3]
        rows = 0
        for v in range(12):
            if any(max(abs(a - b) for a, b in zip(canvas.get("body", "front", u, v)[:3], ref)) <= 45
                   for u in range(8)):
                rows = v + 1
        return rows

    bad = []
    for style in ("long_straight", "long_wavy", "curly", "bob", "ponytail", "short", "pixie", "bun"):
        for length in ("short", "medium", "long", "very_long"):
            attrs = A.validate(dict(base, hair_style=style, hair_length=length))
            bare = body_rows(R.render(observed, attrs, (), mask_override={}))
            masked = body_rows(R.render(observed, attrs, (), mask_override=hair))
            if bare != masked:
                bad.append((style, length, bare, masked))
    assert not bad, f"hair masks changed the drape depth: {bad}"


NO_DRAPE_STYLES = ("short", "pixie", "bob", "ponytail", "bun")


def _hair_seeds():
    from skinmaker import attribute_seeds as AS
    with AS.using(AS.fixture_context()):
        seeds = AS.seed_masks()
    return seeds


def test_hair_style_masks_own_the_head_and_hair_length_masks_own_the_body():
    """Split responsibilities so AND(style, length) is meaningful.

    A style mask describes the silhouette (head); a length mask describes how far
    the torso drape reaches. If a style mask also carried a very_long body, the
    AND could never shorten it, and every style rendered waist-length.
    """
    seeds = _hair_seeds()
    for name, entry in seeds.items():
        if not name.startswith("hair_style."):
            continue
        body_faces = [f for f in entry["L1"] if f.startswith("body.")]
        # No-drape styles must clip body hair explicitly with an all-zero grid;
        # draping styles must not constrain the body at all.
        style = name.split(".", 1)[1]
        if body_faces:
            assert all(not any(any(r) for r in entry["L1"][f]) for f in body_faces), name
            assert style in NO_DRAPE_STYLES, f"{style} should not clip the body"

    for name, entry in seeds.items():
        if not name.startswith("hair_length."):
            continue
        head_faces = {f for f in entry["L1"] if f.startswith("head.")}
        # The nape (head.bottom) is a length feature; the rest of the head is not.
        assert head_faces <= {"head.bottom"}, f"{name} must not constrain head hair: {head_faces}"


def test_hair_masks_reproduce_the_procedural_coverage():
    """Applying the hair masks must not change which cells are hair.

    The masks are seeded by diffing against the procedural render, so clipping to
    them is an identity on coverage. Colours may differ slightly (a masked cell
    is repainted flat instead of keeping the reference strand shading), so this
    compares the hair footprint, which is what the drape policy is about.
    """
    from skinmaker import attributes as A
    from skinmaker import production_qa as Q
    from skinmaker import render as R
    from skinmaker.canvas import rgba, shade

    base = {
        "top_garment": "tee", "bottom_garment": "jeans", "pattern": "plain",
        "sleeve_len": "short", "hair_bbox": [200, 50, 800, 600],
    }
    observed = Q._observed()
    seeds = _hair_seeds()
    hair = {k: v for k, v in seeds.items() if k.startswith("hair_")}

    def footprint(canvas):
        """Body faces only: the drape policy is what the masks must not change.

        Head faces are compared indirectly: the head masks come from the same
        render, and `test_hair_style_masks_own_the_head_*` pins their shape.
        """
        cells = set()
        for face in ("front", "back", "left", "right"):
            ref = shade(rgba(observed.hair.hex), R.FACE_SHADE[face])[:3]
            grid = canvas.layout.face("body", face, 0)
            for v in range(grid.h):
                for u in range(grid.w):
                    px = canvas.get("body", face, u, v)[:3]
                    if max(abs(a - b) for a, b in zip(px, ref)) <= 45:
                        cells.add((face, u, v))
        return cells

    bad = []
    for style in ("long_straight", "long_wavy", "curly", "bob", "ponytail", "short", "pixie", "bun"):
        for length in ("short", "medium", "long", "very_long"):
            attrs = A.validate(dict(base, hair_style=style, hair_length=length))
            bare = footprint(R.render(observed, attrs, (), mask_override={}))
            masked = footprint(R.render(observed, attrs, (), mask_override=hair))
            if bare != masked:
                bad.append(f"{style}+{length}: -{len(bare - masked)} +{len(masked - bare)}")
    assert not bad, f"hair masks changed the hair footprint: {bad}"
