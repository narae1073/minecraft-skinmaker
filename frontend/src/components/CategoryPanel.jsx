import React, { useState } from 'react';

// 설계 §11: LLM 분류 카테고리 — 사람용 칩 + JSON 값 표 (원본 값 그대로).
const KOR = {
  top_garment: { tee: "반팔 티셔츠", hoodie: "후디", jacket: "재킷", shirt: "셔츠", sweater: "스웨터", vest: "조끼", uniform: "교복", apron: "에이프런", overalls: "멜빵바지", dress: "드레스", none: "상의 없음" },
  bottom_garment: { jeans: "청바지", pants: "바지", shorts: "반바지", skirt: "치마", dress: "원피스", none: "하의 없음" },
  pattern: { plain: "무지", vertical_stripe: "세로 줄무늬", horizontal_stripe: "가로 줄무늬", check: "체크", plaid: "플레이드", graphic: "그래픽" },
  sleeve_len: { none: "민소매", short: "반팔", three_quarter: "7부", long: "긴팔" },
  hair_length: { short: "짧은 머리", medium: "중간 머리", long: "긴 머리", very_long: "아주 긴 머리" },
};
const FIELD_KOR = { top_garment: "상의", bottom_garment: "하의", pattern: "무늬", sleeve_len: "소매", hair_length: "머리" };
const FIELDS = ["top_garment", "bottom_garment", "pattern", "sleeve_len", "hair_length"];

export default function CategoryPanel({ attributes, noiseLevel }) {
  const [copied, setCopied] = useState(false);
  if (!attributes) return null;
  const values = attributes.values || {};
  const uncertain = new Set(attributes.uncertain || []);
  const derivedFields = new Set((attributes.derived || []).map((d) => d.split("=")[0]));
  const jsonPayload = { attributes, candidates, noise_level: noiseLevel };
  const label = (f) => KOR[f]?.[values[f]] || values[f];

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(jsonPayload, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* 클립보드 거부 환경은 무시 */ }
  };

  return (
    <div className="category-panel">
      <h3>분류 결과</h3>
      <div className="chips">
        {FIELDS.map((f) => (
          <span key={f} className={`chip ${uncertain.has(f) ? "chip-uncertain" : ""}`}>
            {FIELD_KOR[f]}: {label(f)}
            {derivedFields.has(f) && <em title={(attributes.derived || []).join("; ")}> *</em>}
          </span>
        ))}
      </div>

      <details className="json-details">
        <summary>카테고리 JSON</summary>
        <button type="button" className="copy-json-btn" onClick={copy}>
          {copied ? "복사됨!" : "JSON 복사"}
        </button>
        <table className="json-table">
          <thead><tr><th>항목</th><th>JSON 값</th></tr></thead>
          <tbody>
            {FIELDS.map((f) => (
              <tr key={f} className={uncertain.has(f) ? "row-uncertain" : ""}>
                <td>{f}</td>
                <td>{JSON.stringify(values[f])}{derivedFields.has(f) ? " *" : ""}</td>
              </tr>
            ))}
            <tr><td>uncertain</td><td>{JSON.stringify(attributes.uncertain || [])}</td></tr>
            <tr><td>derived</td><td>{JSON.stringify(attributes.derived || [])}</td></tr>
            <tr><td>coerced</td><td>{JSON.stringify(attributes.coerced || [])}</td></tr>
            <tr><td>noise_level</td><td>{JSON.stringify(noiseLevel)}</td></tr>
          </tbody>
        </table>
      </details>
    </div>
  );
}
