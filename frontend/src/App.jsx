import { useEffect, useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import Skin3DViewer from './components/Skin3DViewer';
import SkinEditor from './components/SkinEditor';
import CategoryPanel from './components/CategoryPanel';
import StepsPanel from './components/StepsPanel';
import CameraCapture from './components/CameraCapture';
import SelectedPhoto from './components/SelectedPhoto';
import CropModal from './components/CropModal';
import './App.css';

const MAX_UPLOAD_EDGE = 1600;

const shrinkImage = (file) => new Promise((resolve) => {
  if (!file.type.startsWith('image/')) { resolve(file); return; }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    const scale = Math.min(1, MAX_UPLOAD_EDGE / Math.max(img.width, img.height));
    if (scale >= 1) { URL.revokeObjectURL(url); resolve(file); return; }
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(img.width * scale);
    canvas.height = Math.round(img.height * scale);
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      URL.revokeObjectURL(url);
      resolve(blob ? new File([blob], 'upload.jpg', { type: 'image/jpeg' }) : file);
    }, 'image/jpeg', 0.87);
  };
  img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
  img.src = url;
});

function App() {
  const mobileSiteUrl = import.meta.env.DEV
    || ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
    ? 'https://skin.achijaser.date'
    : window.location.origin;
  const cameraInputRef = useRef(null);
  const fileInputRef = useRef(null);
  const resultRef = useRef(null);
  const [cameraOpen, setCameraOpen] = useState(false);

  const openCamera = () => {
    const isMobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
      || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    if (isMobile) {
      cameraInputRef.current?.click();
    } else {
      setCameraOpen(true);
    }
  };
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fileError, setFileError] = useState(false);
  const [serverError, setServerError] = useState('');
  const [skins, setSkins] = useState([]); // 현재 결과: {url, flatUrl} 쌍 배열
  const [inputPhoto, setInputPhoto] = useState(null);
  const [editorItem, setEditorItem] = useState(null); // SkinEditor 모달 대상 ({url, flatUrl, steps, model})
  const [noiseLevel, setNoiseLevel] = useState(50); // 노이즈 세기 % (기본 50 — 사용자 결정 2026-10-13)
  const [skinModel, setSkinModel] = useState('classic'); // 체형: classic(4px 팔) | slim(3px 팔)
  const [showSteps, setShowSteps] = useState(false); // 처리 과정 표시 (기본 해제 — 사용자 결정)
  const [hairOverlay, setHairOverlay] = useState('on'); // L2 오버레이 헤어 (기본 켜기 — 사용자 결정 2026-10-21)
  const [hairColorOn, setHairColorOn] = useState(false); // 수동 hair colour override (source-limited notes)
  const [hairColor, setHairColor] = useState('#d4af37');
  const [catInfo, setCatInfo] = useState(null); // 분류 카테고리 {attributes, candidates, noiseLevel} (설계 §11)
  const [steps, setSteps] = useState(null); // 처리 과정 시트 {clean, full} (설계 §12)
  const abortRef = useRef(null);
  const [cropOpen, setCropOpen] = useState(false);
  const [loadingPct, setLoadingPct] = useState(0);
  const [loadingStage, setLoadingStage] = useState('');
  const [cropSize, setCropSize] = useState(null); // no_face 응답의 image_size

  useEffect(() => {
    const abort = () => abortRef.current?.abort();
    window.addEventListener('beforeunload', abort);
    return () => {
      window.removeEventListener('beforeunload', abort);
      abortRef.current?.abort();
    };
  }, []);

  // 결과 섹션은 설정 아래에 있다. 모바일에서 변환 후 결과가 화면 밖이면
  // (미리보기 모달 제거 이후) 결과가 보이도록 스크롤한다.
  useEffect(() => {
    if (!skins.length) return;
    const el = resultRef.current;
    if (!el || el.getBoundingClientRect().top < window.innerHeight) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    el.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }, [skins]);

  // 사이드바 및 스킨 기록 관련 상태
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [skinHistory, setSkinHistory] = useState([]); // 누적 스킨 보관
  const [selectedSkins, setSelectedSkins] = useState([]); // 삭제를 위해 선택된 스킨의 인덱스 배열

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    
    if (selectedFile) {
      if (!selectedFile.type.startsWith('image/')) {
        setFileError(true);
        setFile(null);
        e.target.value = '';
        
        setTimeout(() => {
          setFileError(false);
        }, 2500);
        return;
      }
      shrinkImage(selectedFile).then(setFile);
    }
  };

  const handleGenerate = async (cropBox = null) => {
    if (!file) {
      alert('사진을 선택해주세요!');
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoadingPct(0);
    setLoadingStage('사진을 올리는 중이에요');
    setIsLoading(true);
    setSkins([]);
    setInputPhoto(null);
    setServerError('');
    setCatInfo(null);
    setSteps(null);

    const showFailure = (detail) => {
      setServerError(detail.message || '스킨 생성에 실패했어요.');
      if (detail.can_crop && detail.image_size) {
        setCropSize(detail.image_size);
        setCropOpen(true);
      }
    };

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('noise_level', String(noiseLevel / 100));
      formData.append('steps', showSteps ? '1' : '0');
      formData.append('hair_overlay', hairOverlay);
      formData.append('skin_model', skinModel);
      if (hairColorOn) formData.append('hair_color', hairColor);
      if (cropBox) formData.append('crop', JSON.stringify(cropBox));

      const response = await fetch('/api/v1/generate-skin', {
        method: 'POST',
        body: formData,
        signal: controller.signal,
        headers: { Accept: 'text/event-stream' },
      });

      const contentType = response.headers.get('content-type') || '';
      let data = null;
      if (contentType.includes('text/event-stream')) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let streamError = null;
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let split;
          while ((split = buffer.indexOf('\n\n')) >= 0) {
            const chunk = buffer.slice(0, split);
            buffer = buffer.slice(split + 2);
            const event = (chunk.match(/^event: (.+)$/m) || [])[1];
            const raw = (chunk.match(/^data: (.+)$/m) || [])[1];
            if (!raw) continue;
            let obj;
            try { obj = JSON.parse(raw); } catch { continue; }
            if (event === 'progress') {
              setLoadingPct(obj.pct ?? 0);
              setLoadingStage(obj.label || '');
            } else if (event === 'result') {
              data = obj;
            } else if (event === 'error') {
              // 서버 HTTPException.detail 이 그대로 온다 — 문자열이거나 {message, can_crop, image_size} 객체
              streamError = typeof obj.message === 'string' ? { message: obj.message } : (obj.message || {});
            }
          }
        }
        if (streamError) { showFailure(streamError); return; }
        if (!data) { setServerError('응답이 비어 있어요. 다시 시도해주세요.'); return; }
      } else {
        data = await response.json().catch(() => null);
      }
      if (!response.ok) {
        const detail = data?.detail || {};
        showFailure({ ...detail, message: detail.message || data?.message || `서버 오류 (${response.status})` });
        return;
      }
      if (data.status === 'success') {
        // 스킨을 {url, flatUrl} 쌍으로 보관 — Edit Skin 토글이 두 변형을 스왑한다 (설계 §5)
        const resultModel = data.data.skin_model || 'classic';
        const pairs = (data.data.skins || []).map((url, i) => ({
          url,
          flatUrl: (data.data.skins_flat || [])[i] || null,
          varied: (data.data.candidates || [])[i]?.varied || "",
          steps: data.data.steps || null, // 이 생성의 처리 과정 시트 — 사이드바 편집이 자기 세대의 시트를 연다 (후속 검토 1)
          model: resultModel, // 3D 뷰어 체형 (classic | slim)
        }));
        setSkins(pairs);
        setCatInfo({
          attributes: data.data.attributes || null,
          candidates: data.data.candidates || [],
          noiseLevel: data.data.noise_level,
        });
        setSteps(data.data.steps || null);
        setInputPhoto(data.data.input || null);
        // 스킨 생성이 완료되면 기존 기록(skinHistory) 뒤에 새 스킨들을 추가
        setSkinHistory(prev => [...prev, ...pairs]);
      } else {
        setServerError(data?.message || '스킨 생성 실패');
      }
    } catch (error) {
      if (error?.name === 'AbortError') return;
      console.error(error);
      setServerError('서버에 연결하지 못했어요. 백엔드가 켜져 있는지 확인해주세요.');
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setIsLoading(false);
    }
  };

  // 체크박스 선택 토글 기능
  const handleToggleSelect = (index) => {
    if (selectedSkins.includes(index)) {
      setSelectedSkins(prev => prev.filter(i => i !== index));
    } else {
      setSelectedSkins(prev => [...prev, index]);
    }
  };

  // 선택된 스킨 삭제 기능
  const handleDeleteSelected = () => {
    if (selectedSkins.length === 0) {
      alert('삭제할 스킨을 먼저 선택해주세요.');
      return;
    }
    // 선택되지 않은 인덱스의 스킨들만 남김
    setSkinHistory(prev => prev.filter((_, idx) => !selectedSkins.includes(idx)));
    setSelectedSkins([]); // 선택 상태 초기화
  };

  return (
    <>
      {/* 화면 왼쪽 상단: 목록 열기 버튼 */}
      <button className="sidebar-toggle-btn" onClick={() => setIsSidebarOpen(true)}>
        ☰ 스킨 목록
      </button>

      {/* 왼쪽 사이드바 (목록 창) */}
      <div className={`sidebar ${isSidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <h3>생성된 스킨 목록</h3>
          <button className="close-btn" onClick={() => setIsSidebarOpen(false)}>✕</button>
        </div>
        
        <div className="sidebar-actions">
          <button className="delete-btn" onClick={handleDeleteSelected}>선택 파일 지우기</button>
        </div>

        <div className="sidebar-content">
          {skinHistory.length === 0 ? (
            <p className="empty-msg">아직 생성된 스킨이 없습니다.</p>
          ) : (
            <ul className="skin-list">
              {skinHistory.map((skin, index) => (
                <li key={index} className="skin-list-item">
                  <input
                    type="checkbox"
                    className="skin-checkbox"
                    checked={selectedSkins.includes(index)}
                    onChange={() => handleToggleSelect(index)}
                  />
                  {/* 스킨 썸네일 (64x64 이미지를 픽셀 깨짐 없이 보여줌) */}
                  <img src={skin.url} alt={`스킨 ${index + 1}`} className="skin-thumbnail" />
                  <a href={skin.url} download={`skin_${index + 1}.png`} className="sidebar-download-link">
                    스킨 {index + 1}
                  </a>
                  <button className="edit-btn" onClick={() => { setEditorItem(skin); setIsSidebarOpen(false); }}>
                    편집
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* 에러 및 로딩 오버레이 */}
      {fileError && (
        <div className="loading-overlay" onClick={() => setFileError(false)}>
          <h2>파일 오류!</h2>
          <p>사진 파일을 첨부해주세요!</p>
        </div>
      )}

      {serverError && (
        <div className="loading-overlay" onClick={() => setServerError('')}>
          <h2>스킨 생성 실패</h2>
          <p>{serverError}</p>
          <p className="empty-msg">눌러서 닫기</p>
        </div>
      )}

      {isLoading && (
        <div className="loading-overlay" role="status" aria-live="polite">
          <div className="loading-card">
            <h2>스킨을 만들고 있어요</h2>
            <div
              className="loading-bar"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(loadingPct)}
            >
              <div className="loading-bar-fill" style={{ width: `${loadingPct}%` }} />
            </div>
            <p className="loading-stage">{loadingStage || '준비 중이에요'}</p>
          </div>
        </div>
      )}

      {/* 메인 화면 컨테이너 */}
      <div className="container">
        <div className="site-header">
          <h1>마인크래프트 스킨 메이커</h1>
          <a className="mobile-site-qr" href={mobileSiteUrl} aria-label="모바일로 사이트 열기">
            <QRCodeSVG value={mobileSiteUrl} size={104} marginSize={4} level="M" title="모바일 접속 QR코드" />
            <span>모바일로 열기</span>
          </a>
        </div>
        <p>당신의 전신 사진을 첨부해주세요!</p>
        
        <div className="upload-section">
          <input
            ref={cameraInputRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            onChange={handleFileChange}
            onClick={(e) => { e.currentTarget.value = ''; }}
          />
          <div className="upload-panel camera-panel">
            <p className="camera-hint">PC 웹캠 또는 모바일 카메라로 촬영할 수 있어요.</p>
            <button
              type="button"
              onClick={openCamera}
              disabled={isLoading}
              className="generate-btn camera-btn"
            >
              카메라로 사진 찍어 업로드
            </button>
          </div>
          <div className="upload-panel">
            <input ref={fileInputRef} type="file" accept="image/jpeg, image/png" onChange={handleFileChange} hidden />
            <div className="file-picker">
              <button type="button" className="file-picker-btn" onClick={() => fileInputRef.current?.click()} disabled={isLoading}>파일 선택</button>
              <span className="file-picker-name" title={file?.name}>{file?.name || '선택된 파일 없음'}</span>
            </div>
            <button onClick={() => handleGenerate()} disabled={isLoading} className="generate-btn">
              {isLoading ? '생성 중...' : '스킨 변환하기'}
            </button>
          </div>
          {file && <SelectedPhoto file={file} />}
        </div>

        {cameraOpen && (
          <CameraCapture
            onCapture={(photo) => { setFile(photo); setCameraOpen(false); }}
            onClose={() => setCameraOpen(false)}
            onChooseFile={() => { cameraInputRef.current?.click(); setCameraOpen(false); }}
          />
        )}

        <div className="config-section">
          <h3>설정</h3>
          <div className="config-row">
            <label htmlFor="noise-level">픽셀 질감</label>
            <input
              id="noise-level"
              aria-describedby="noise-help"
              type="range"
              min="0"
              max="100"
              step="5"
              value={noiseLevel}
              onChange={(e) => setNoiseLevel(Number(e.target.value))}
            />
            <span className="noise-readout">{noiseLevel}%</span>
          </div>
          <p id="noise-help" className="config-help">높일수록 픽셀마다 밝기 차이를 더해 질감을 표현해요. 0%는 이 효과를 끕니다.</p>
          <div className="config-row">
            <label htmlFor="skin-model">스킨 모델</label>
            <select
              id="skin-model"
              aria-describedby="skin-model-help"
              value={skinModel}
              onChange={(e) => setSkinModel(e.target.value)}
            >
              <option value="classic">클래식 (팔 4px)</option>
              <option value="slim">슬림 (팔 3px)</option>
            </select>
          </div>
          <p id="skin-model-help" className="config-help">클래식은 기본 체형, 슬림은 팔이 3px 얇은 체형이에요.</p>
          <div className="config-row">
            <label htmlFor="hair-color">
              <input
                id="hair-color-on"
                type="checkbox"
                checked={hairColorOn}
                onChange={(e) => setHairColorOn(e.target.checked)}
              />
              머리색 직접 지정
            </label>
            <input
              id="hair-color"
              type="color"
              value={hairColor}
              onChange={(e) => setHairColor(e.target.value)}
              aria-label="머리색"
            />
          </div>
          <p className="config-help">사진에서 금발을 못 읽는 경우(머리가 가려짐) 직접 지정해요.</p>
          <div className="config-row">
            <label htmlFor="show-steps">
              <input
                id="show-steps"
                type="checkbox"
                checked={showSteps}
                onChange={(e) => setShowSteps(e.target.checked)}
              />
              처리 과정 표시 <small>(끄면 단계 이미지를 만들지 않아요)</small>
            </label>
          </div>
          <div className="config-row">
            <label htmlFor="hair-overlay">머리카락 볼륨</label>
            <select
              id="hair-overlay"
              aria-describedby="hair-overlay-help"
              value={hairOverlay}
              onChange={(e) => setHairOverlay(e.target.value)}
            >
              <option value="on">볼륨 더하기</option>
              <option value="off">기본 두께</option>
            </select>
          </div>
          <p id="hair-overlay-help" className="config-help">머리카락을 바깥쪽에 한 겹 더 그려 입체감을 줘요. 앞머리와 긴 머리도 더 도드라져 보여요.</p>
        </div>

        {skins.length > 0 && (
          <div className="result-section" ref={resultRef}>
            <h2>생성된 64×64 스킨 후보 {skins.length}종</h2>
            <p className="compare-hint">원본 사진을 왼쪽에 두고 스킨을 비교해보세요 (3D 뷰어에서 회전도 가능)</p>
            <div className="compare-grid">
              {inputPhoto && (
                <div className="skin-card input-card">
                  <h3>원본 사진</h3>
                  <img
                    src={inputPhoto}
                    alt="입력 사진"
                    className="input-photo"
                  />
                  <div className="card-actions">
                    <a href={inputPhoto} download="input_photo.png" className="download-btn">
                      사진 다운로드
                    </a>
                  </div>
                </div>
              )}
              {skins.map((skin, index) => (
                <div key={index} className="skin-card">
                  <h3>후보 {index + 1}</h3>
                  {skin.varied && skin.varied !== "as-answered" && (
                    <p className="varied-note">{skin.varied}</p>
                  )}
                  <Skin3DViewer skinUrl={skin.url} model={skin.model} />
                  <div className="card-actions">
                    <a href={skin.url} download={`skin_option_${index + 1}.png`} className="download-btn">
                      스킨 다운로드
                    </a>
                  </div>
                </div>
              ))}
            </div>
            {/* 순서 (사용자 지시): 원본+후보 행 → 분류 결과+처리 과정 행 */}
            <div className={`analysis-row ${steps?.clean ? "" : "analysis-single"}`}>
              <CategoryPanel attributes={catInfo?.attributes} noiseLevel={catInfo?.noiseLevel} />
              <StepsPanel steps={steps} />
            </div>
          </div>
        )}

        {editorItem && (
          <SkinEditor skin={editorItem} steps={editorItem.steps} onClose={() => setEditorItem(null)} />
        )}

        {cropOpen && cropSize && file && (
          <CropModal
            file={file}
            imageSize={cropSize}
            onApply={(box) => { setCropOpen(false); handleGenerate(box); }}
            onClose={() => setCropOpen(false)}
          />
        )}

        <footer className="footer">
          &copy; 2026 몬태규. All rights reserved.
          <br />
          <small>공개 데모입니다. 민감한 사진은 올리지 마세요. 업로드 파일은 보존 기간(기본 14일) 후 삭제됩니다.</small>
        </footer>
      </div>
    </>
  );
}

export default App;
