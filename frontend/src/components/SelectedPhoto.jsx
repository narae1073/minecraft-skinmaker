import { useEffect, useRef } from 'react';

export default function SelectedPhoto({ file }) {
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
    </div>
  );
}
