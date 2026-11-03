import { useEffect, useRef } from 'react';

// 모달/오버레이 공통 동작: 열릴 때 대화상자에 포커스를 옮기고, Escape 로 닫고,
// 닫히면 이전에 포커스가 있던 요소로 돌려보낸다.
// `active` 가 false 면 아무 것도 하지 않는다 (조건부 렌더링 오버레이용).
export default function useDialog(ref, active, onClose) {
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; });

  useEffect(() => {
    if (!active) return undefined;
    const prev = document.activeElement;
    ref.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') closeRef.current(); };
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      prev?.focus?.();
    };
  }, [active, ref]);
}
