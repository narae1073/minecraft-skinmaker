import { useEffect, useRef } from 'react';

export default function SelectedPhoto({ file, disabled = false, onReplace, onRemove }) {
  const imageRef = useRef(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    imageRef.current.src = url;
    return () => URL.revokeObjectURL(url);
  }, [file]);

  return (
    <div className="selected-photo" role="status">
      <img ref={imageRef} alt="선택한 원본 사진" />
      <span>선택한 사진: {file.name}</span>
      <div className="selected-photo-actions">
        <button type="button" className="file-picker-btn" onClick={onReplace} disabled={disabled}>사진 바꾸기</button>
        <button type="button" className="file-picker-btn" onClick={onRemove} disabled={disabled}>지우기</button>
      </div>
    </div>
  );
}
