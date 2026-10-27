import { useEffect, useRef, useState } from 'react';

export default function CameraCapture({ onCapture, onClose, onChooseFile }) {
  const dialogRef = useRef(null);
  const videoRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    let cancelled = false;
    let stream;
    dialog.showModal();

    async function startCamera() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('카메라를 사용하려면 HTTPS 또는 localhost로 접속해주세요. 지원되지 않는 브라우저에서는 파일을 선택해주세요.');
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        if (cancelled) {
          stream.getTracks().forEach(track => track.stop());
          return;
        }
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      } catch (err) {
        if (cancelled) return;
        stream?.getTracks().forEach(track => track.stop());
        if (err.name === 'NotAllowedError') {
          setError('카메라 권한이 필요해요. 브라우저의 사이트 설정에서 카메라를 허용한 뒤 다시 열어주세요.');
        } else if (err.name === 'NotFoundError') {
          setError('연결된 웹캠을 찾지 못했어요. 카메라 연결을 확인하거나 사진 파일을 선택해주세요.');
        } else {
          setError('카메라를 열지 못했어요. 다른 앱에서 사용 중인지 확인하거나 사진 파일을 선택해주세요.');
        }
      }
    }
    startCamera();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach(track => track.stop());
      dialog.close();
      previousFocus?.focus();
    };
  }, []);

  function takePhoto() {
    const video = videoRef.current;
    if (!video.videoWidth || !video.videoHeight) return;
    setSaving(true);
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    canvas.toBlob(blob => {
      if (!dialogRef.current?.open) return;
      if (!blob) {
        setError('사진을 저장하지 못했어요. 카메라를 다시 열어주세요.');
        setSaving(false);
        return;
      }
      onCapture(new File([blob], `camera-${Date.now()}.jpg`, { type: 'image/jpeg' }));
    }, 'image/jpeg', 0.92);
  }

  return (
    <dialog ref={dialogRef} className="camera-dialog" aria-labelledby="camera-title" onCancel={onClose}>
      <h2 id="camera-title">카메라로 사진 찍기</h2>
      <p>전신이 화면에 들어오도록 맞춘 뒤 촬영해주세요.</p>
      {error ? <p role="alert">{error}</p> : (
        <>
          <video ref={videoRef} autoPlay playsInline muted onCanPlay={() => setReady(true)} />
          {!ready && <p role="status">카메라 연결 중… 권한 요청을 확인해주세요.</p>}
        </>
      )}
      <div className="camera-actions">
        {!error && <button className="generate-btn" onClick={takePhoto} disabled={!ready || saving}>촬영해서 사용하기</button>}
        {error && <button className="generate-btn" onClick={onChooseFile}>사진 파일 선택</button>}
        <button className="edit-btn" onClick={onClose}>닫기</button>
      </div>
    </dialog>
  );
}
