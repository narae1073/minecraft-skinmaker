import { useState } from 'react';
import Skin3DViewer from './Skin3DViewer';
import StepsPanel from './StepsPanel';

// 스킨 편집기 (설계 §5): 3D 렌더러의 확장 단계. 옵션 상태에
// 이후 옷 변경·피부 톤 등이 같은 자리에 붙는다 (v1은 신발 2톤뿐).
export default function SkinEditor({ skin, steps, onClose }) {
  const [options, setOptions] = useState({ two_tone: true }); // 기본 ON
  const texture = options.two_tone ? skin.url : (skin.flatUrl || skin.url);
  const name = (texture || 'skin.png').split('/').pop().replace('.png', '');

  return (
    <div className="editor-overlay" onClick={onClose}>
      <div className="editor-modal" onClick={(e) => e.stopPropagation()}>
        <div className="editor-header">
          <h3>스킨 편집</h3>
          <button className="close-btn" onClick={onClose}>✕</button>
        </div>
        <div className="editor-body">
          <Skin3DViewer skinUrl={texture} width={360} height={480} />
        </div>
        <div className="editor-options">
          <label className="option-row">
            <span>신발 2톤 (바닥 행 강조)</span>
            <input
              type="checkbox"
              checked={options.two_tone}
              onChange={(e) => setOptions((o) => ({ ...o, two_tone: e.target.checked }))}
            />
          </label>
        </div>
        <StepsPanel steps={steps} compact />
        <a href={texture} download={`${name}.png`} className="download-btn editor-download">
          현재 스킨 다운로드
        </a>
      </div>
    </div>
  );
}
