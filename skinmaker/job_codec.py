"""JSON round-trip for the renderer's dataclasses (observed colours, hair stencil,
attributes). A stored job must re-render exactly, so decoding restores tuples and
nested dataclasses from the type hints instead of leaving lists behind."""
from __future__ import annotations

import base64
import dataclasses
import io
import types
import typing
from typing import Any

from PIL import Image

from . import attributes as A
from . import colors as C
from . import hairstencil as HS
from . import texture as TX

_DATACLASSES = {cls.__name__: cls for cls in (C.ColorSample, C.CoverEstimate, C.ObservedColors,
                                              HS.HairStencil, A.Attributes, TX.FabricTexture)}


def encode(value: Any) -> Any:
    if isinstance(value, Image.Image):
        buf = io.BytesIO()
        value.save(buf, format="PNG")
        return {"__png__": base64.b64encode(buf.getvalue()).decode("ascii")}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: encode(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {str(k): encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    return value


def decode(data: Any, hint: Any) -> Any:
    if data is None:
        return None
    if isinstance(data, dict) and "__png__" in data:
        return Image.open(io.BytesIO(base64.b64decode(data["__png__"]))).copy()
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin in (typing.Union, types.UnionType):
        inner = [a for a in args if a is not type(None)]
        return decode(data, inner[0]) if inner else data
    if isinstance(hint, type) and dataclasses.is_dataclass(hint):
        hints = typing.get_type_hints(hint, localns=_DATACLASSES)
        kwargs = {}
        for f in dataclasses.fields(hint):
            if f.name in data:
                kwargs[f.name] = decode(data[f.name], hints.get(f.name, Any))
        return hint(**kwargs)
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(v, args[0]) for v in data)
        if args:
            return tuple(decode(v, a) for v, a in zip(data, args))
        return tuple(data)
    if origin is dict:
        value_hint = args[1] if len(args) == 2 else Any
        return {k: decode(v, value_hint) for k, v in data.items()}
    if origin is list:
        return [decode(v, args[0] if args else Any) for v in data]
    return data


def dump_dataclass(obj: Any) -> dict:
    return encode(obj)


def load_dataclass(data: dict, cls: type) -> Any:
    return decode(data, cls)


def registry() -> dict[str, type]:
    return dict(_DATACLASSES)
