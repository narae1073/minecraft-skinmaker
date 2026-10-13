import React, { useState } from 'react';

// 설계 §12: 처리 과정 이미지 — 간단/QA 토글, 접이식, 원본 크기 링크.
export default function StepsPanel({ steps, compact = false }) {
  const [mode, setMode] = useState("clean"); // "clean" | "full"
  if (!steps?.clean) return null;
  const url = mode === "full" ? steps.full : steps.clean;

  return (
    <details className={`steps-details ${compact ? "steps-compact" : ""}`}>
      <summary>처리 과정</summary>
      <div className="steps-toggle">
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
        <a href={url} target="_blank" rel="noreferrer" className="steps-fullsize-link">
          원본 크기 보기
        </a>
      </div>
      {url && (
        <a href={url} target="_blank" rel="noreferrer">
          <img src={url} alt="파이프라인 처리 과정" className="steps-image" loading="lazy" />
        </a>
      )}
    </details>
  );
}
