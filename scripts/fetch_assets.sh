#!/usr/bin/env bash
# Download the gitignored model assets.
#
#   scripts/fetch_assets.sh               # YuNet + SCHP parser
#   scripts/fetch_assets.sh --yunet-only  # CI / tests
#   scripts/fetch_assets.sh --schp-only
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YUNET="$ROOT/assets/face_detection_yunet_2023mar.onnx"
SCHP="$ROOT/out/models/schp-atr-18-int8-static.onnx"
YUNET_URL="https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SCHP_URL="https://huggingface.co/pirocheto/schp-atr-18/resolve/main/onnx/schp-atr-18-int8-static.onnx?download=true"

want_yunet=1
want_schp=1
case "${1:-}" in
  --yunet-only) want_schp=0 ;;
  --schp-only) want_yunet=0 ;;
  "") ;;
  *) echo "usage: $0 [--yunet-only|--schp-only]" >&2; exit 2 ;;
esac

fetch() {
  local url="$1" dest="$2"
  if [ -s "$dest" ]; then
    echo "ok      $dest"
    return
  fi
  mkdir -p "$(dirname "$dest")"
  echo "fetch   $dest"
  curl -sSLf --retry 3 -o "$dest.part" "$url"
  mv "$dest.part" "$dest"
  echo "done    $dest ($(du -h "$dest" | cut -f1))"
}

[ "$want_yunet" = 1 ] && fetch "$YUNET_URL" "$YUNET"
[ "$want_schp" = 1 ] && fetch "$SCHP_URL" "$SCHP"
