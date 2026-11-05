import { useEffect, useRef, useState } from 'react';
import useDialog from '../useDialog';

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export default function CropModal({ file, imageSize, onApply, onClose }) {
  const [box, setBox] = useState(() => {
    const [w, h] = imageSize;
    return { x: Math.round(w * 0.10), y: Math.round(h * 0.03), w: Math.round(w * 0.80), h: Math.round(h * 0.94) };
  });
  const [url] = useState(() => URL.createObjectURL(file));
  const [drag, setDrag] = useState(null);
  const frameRef = useRef(null);
  const dialogRef = useRef(null);
  useDialog(dialogRef, true, onClose);

  useEffect(() => () => URL.revokeObjectURL(url), [url]);

  if (!box) return null;
  const [iw, ih] = imageSize;

  const begin = (mode, e) => {
    e.preventDefault();
    e.stopPropagation();
    const frame = frameRef.current.getBoundingClientRect();
    setDrag({ mode, startX: e.clientX, startY: e.clientY, box: { ...box }, frame });
  };

  const move = (e) => {
    if (!drag) return;
    const dx = (e.clientX - drag.startX) / drag.frame.width * iw;
    const dy = (e.clientY - drag.startY) / drag.frame.height * ih;
    const b = drag.box;
    let next = { ...b };
    if (drag.mode === 'move') {
      next.x = clamp(b.x + dx, 0, iw - b.w);
      next.y = clamp(b.y + dy, 0, ih - b.h);
    } else {
      if (drag.mode.includes('e')) next.w = clamp(b.w + dx, 48, iw - b.x);
      if (drag.mode.includes('s')) next.h = clamp(b.h + dy, 48, ih - b.y);
      if (drag.mode.includes('w')) { const x = clamp(b.x + dx, 0, b.x + b.w - 48); next.x = x; next.w = b.w + (b.x - x); }
      if (drag.mode.includes('n')) { const y = clamp(b.y + dy, 0, b.y + b.h - 48); next.y = y; next.h = b.h + (b.y - y); }
    }
    setBox(next);
  };

  const end = () => setDrag(null);

  return (
    <div className="crop-backdrop" onPointerMove={move} onPointerUp={end} onPointerLeave={end}>
      <div ref={dialogRef} tabIndex={-1} role="dialog" aria-modal="true" aria-labelledby="crop-title" className="crop-modal">
        <div id="crop-title" className="crop-title">얼굴을 찾기 어려워요. 인물이 전신에 들어오게 크롭해 주세요.</div>
        <div className="crop-frame" ref={frameRef}>
          <img src={url} alt="crop source" draggable={false} />
          <div
            className="crop-box"
            style={{
              left: `${(box.x / iw) * 100}%`, top: `${(box.y / ih) * 100}%`,
              width: `${(box.w / iw) * 100}%`, height: `${(box.h / ih) * 100}%`,
            }}
            onPointerDown={(e) => begin('move', e)}
          >
            {['nw', 'ne', 'sw', 'se'].map((h) => (
              <span key={h} className={`crop-handle ${h}`} onPointerDown={(e) => begin(h, e)} />
            ))}
          </div>
        </div>
        <div className="crop-actions">
          <button type="button" onClick={() => onApply(box)}>이 크롭으로 다시 시도</button>
          <button type="button" onClick={onClose}>취소</button>
        </div>
      </div>
    </div>
  );
}
