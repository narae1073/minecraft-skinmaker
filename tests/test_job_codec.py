"""Job records must round-trip the renderer inputs exactly (observed colours,
hair stencil, attributes), so a stored skin can be re-rendered later."""
from __future__ import annotations

from skinmaker import colors as C
from skinmaker import hairstencil as HS
from skinmaker import attributes as A
from skinmaker import job_codec as JC
from skinmaker import production_qa as Q


def test_observed_roundtrip_with_hair_stencil_and_cover():
    base = Q._observed()
    stencil = HS.HairStencil(
        front=tuple(tuple(((u + v) % 3 == 0) for u in range(8)) for v in range(8)),
        top_hair=True,
        side_profiles={"right": (8, 8, 7, 6, 5, 4, 3, 2), "left": (2, 3, 4, 5, 6, 7, 8, 8)},
        body_rows=4,
        bottom=tuple(tuple(False for _ in range(8)) for _ in range(8)),
        front_body_rows=2,
        back_body_rows=3,
        bangs_evidence=True,
    )
    cover = C.CoverEstimate(sleeve_len="short", bottom_len="long", arms_known=2, legs_known=2)
    observed = C.ObservedColors(
        base.skin, base.hair, base.top, base.bottom, base.wb_gain, base.wb_confident,
        base.skin_chroma, base.top_alt, base.stripe, cover, base.bottom_plausible, base.shoe,
        base.lower_body_seen, stencil,
    )
    decoded = JC.decode(JC.encode(observed), C.ObservedColors)
    assert decoded == observed
    assert isinstance(decoded.hair_stencil.front, tuple)
    assert isinstance(decoded.wb_gain, tuple)


def test_attributes_roundtrip_keeps_tuples():
    attrs = A.validate({"top_garment": "tee", "hair_bbox": [200, 50, 800, 600]})
    decoded = JC.decode(JC.encode(attrs), A.Attributes)
    assert decoded.values == attrs.values
    assert decoded.hair_bbox == (200, 50, 800, 600)


def test_fabric_texture_images_roundtrip_pixel_exact():
    from PIL import Image
    from skinmaker import texture as TX
    body = Image.new("RGB", (8, 12), (10, 200, 30))
    body.putpixel((3, 4), (255, 0, 1))
    tex = TX.FabricTexture(body=body, side=Image.new("RGB", (4, 12), (1, 2, 3)),
                           leg=Image.new("RGB", (4, 12), (4, 5, 6)), complexity=12.5, bbox=(1, 2, 3, 4))
    base = Q._observed()
    observed = C.ObservedColors(base.skin, base.hair, base.top, base.bottom, base.wb_gain, base.wb_confident,
                                base.skin_chroma, base.top_alt, base.stripe, None, base.bottom_plausible,
                                base.shoe, base.lower_body_seen, None, top_texture=tex)
    decoded = JC.decode(JC.encode(observed), C.ObservedColors)
    assert decoded.top_texture.body.tobytes() == body.tobytes()
    assert decoded.top_texture.body.getpixel((3, 4)) == (255, 0, 1)
    assert decoded.top_texture.complexity == 12.5
    assert decoded.top_texture.bbox == (1, 2, 3, 4)
