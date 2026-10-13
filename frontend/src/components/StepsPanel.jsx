import { useEffect, useState } from 'react';

// 설계 §12 개정 + UI 정리: 인라인은 작은 썸네일, 클릭하면 라이트박스 모달.
// 라이트박스는 자체 스크롤을 갖는다 — 페이지 스크롤을 붙잡지 않는다.
// 훅은 조기 return 위에 (rules-of-hooks: 렌더마다 같은 순서·개수).
export default function StepsPanel({ steps, compact = false }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("clean"); // "clean" | "full"
  const hasSteps = Boolean(steps?.clean);

  useEffect(() => {
    if (!open) return;
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (!hasSteps) return null;
  const url = mode === "full" ? steps.full : steps.clean;

  return (
    <div className={`steps-block ${compact ? "steps-compact" : ""}`}>
      <button type="button" className="steps-thumb-btn" onClick={() => setOpen(true)}>
        <img src={steps.clean} alt="처리 과정 썸네일" className="steps-thumb" />
        <span className="steps-thumb-label">처리 과정 보기</span>
      </button>

      {open && (
        <div className="lightbox-overlay" onClick={() => setOpen(false)}>
          <div className="lightbox" onClick={(e) => e.stopPropagation()}>
            <div className="lightbox-head">
              <h3>처리 과정</h3>
              <div className="lightbox-modes">
                <button
                  type="button"
                  className={`steps-mode-btn ${mode === "clean" ? "active" : ""}`}
                  onClick={() => setMode("clean")}
                >
                  간단
                </button>
                <button
                  type="button"
                  className={`steps-mode-btn ${mode === "full" ? "active" : ""}`}
                  onClick={() => setMode("full")}
                >
                  전체 QA
                </button>
              </div>
              <button type="button" className="lightbox-close" onClick={() => setOpen(false)}>
                ✕
              </button>
            </div>
            <div className="lightbox-body">
              <img src={url} alt="파이프라인 처리 과정" className="steps-image" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
