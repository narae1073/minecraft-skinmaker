import { useEffect, useRef, useState } from 'react';
import Skin3DViewer from './Skin3DViewer';

export default function SkinPreview({ skins, onClose }) {
  const dialogRef = useRef(null);
  const [selected, setSelected] = useState(0);
  const skin = skins[selected];

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      previousFocus?.focus();
    };
  }, []);

  return (
    <dialog className="skin-preview-dialog" ref={dialogRef} aria-labelledby="skin-preview-title" onCancel={onClose}>
      <h2 id="skin-preview-title">완성된 스킨 미리보기</h2>
      <p>스킨을 돌려보고 마음에 들면 다운로드하세요.</p>
      {skins.length > 1 && (
        <label className="preview-candidate">
          미리볼 스킨
          <select value={selected} onChange={e => setSelected(Number(e.target.value))}>
            {skins.map((item, index) => <option key={item.url} value={index}>후보 {index + 1}</option>)}
          </select>
        </label>
      )}
      <div className="preview-model">
        <Skin3DViewer skinUrl={skin.url} model={skin.model || 'classic'} width={200} height={300} />
      </div>
      <div className="preview-actions">
        <a className="download-btn" href={skin.url} download={`skin_option_${selected + 1}.png`}>이 스킨 다운로드</a>
        <button type="button" className="edit-btn" onClick={onClose}>다운로드하지 않고 닫기</button>
      </div>
      <p className="preview-note">닫아도 결과는 아래에 남아 있어요. 나중에 다시 다운로드할 수 있습니다.</p>
    </dialog>
  );
}
