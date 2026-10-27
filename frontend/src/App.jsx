import { useRef, useState } from 'react';
import { QRCodeSVG } from 'qrcode.react';
import Skin3DViewer from './components/Skin3DViewer';
import SkinEditor from './components/SkinEditor';
import CategoryPanel from './components/CategoryPanel';
import StepsPanel from './components/StepsPanel';
import CameraCapture from './components/CameraCapture';
import SkinPreview from './components/SkinPreview';
import SelectedPhoto from './components/SelectedPhoto';
import './App.css';

function App() {
  const mobileSiteUrl = import.meta.env.DEV
    || ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
    ? 'https://skin.achijaser.date'
    : window.location.origin;
  const cameraInputRef = useRef(null);
  const fileInputRef = useRef(null);
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
  const [previewOpen, setPreviewOpen] = useState(false);
  const [inputPhoto, setInputPhoto] = useState(null);
  const [editorItem, setEditorItem] = useState(null); // SkinEditor 모달 대상 ({url, flatUrl, steps, model})
  const [noiseLevel, setNoiseLevel] = useState(50); // 노이즈 세기 % (기본 50 — 사용자 결정 2026-10-13)
  const [skinModel, setSkinModel] = useState('classic'); // 체형: classic(4px 팔) | slim(3px 팔)
  const [showSteps, setShowSteps] = useState(false); // 처리 과정 표시 (기본 해제 — 사용자 결정)
  const [hairSource, setHairSource] = useState('mask'); // 머리 실루엣 근원 (Tier 0 기본 mask — 사용자 결정 2026-10-15)
  const [hairSymmetry, setHairSymmetry] = useState('symmetrized'); // 머리 대칭 (기본 대칭화 — 사용자 결정)
  const [hairOverlay, setHairOverlay] = useState('on'); // L2 오버레이 헤어 (기본 켜기 — 사용자 결정 2026-10-21)
  const [catInfo, setCatInfo] = useState(null); // 분류 카테고리 {attributes, candidates, noiseLevel} (설계 §11)
  const [steps, setSteps] = useState(null); // 처리 과정 시트 {clean, full} (설계 §12)

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
      setFile(selectedFile);
    }
  };

  const handleGenerate = async () => {
    if (!file) {
      alert('사진을 선택해주세요!');
      return;
    }

    setIsLoading(true);
    setPreviewOpen(false);
    setSkins([]);
    setInputPhoto(null);
    setServerError('');
    setCatInfo(null);
    setSteps(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('noise_level', String(noiseLevel / 100));
    formData.append('steps', showSteps ? '1' : '0');
    formData.append('hair_source', hairSource);
    formData.append('hair_symmetry', hairSymmetry);
    formData.append('hair_overlay', hairOverlay);
    formData.append('skin_model', skinModel);

    try {
      const response = await fetch('/api/v1/generate-skin', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const msg = data?.detail?.message || data?.message || `서버 오류 (${response.status})`;
        setServerError(msg);
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
        setPreviewOpen(pairs.length > 0);
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
      console.error(error);
      setServerError('서버에 연결하지 못했어요. 백엔드가 켜져 있는지 확인해주세요.');
    } finally {
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
        <div className="loading-overlay">
          <div className="spinner"></div>
          <h2>로딩중</h2>
          <p>스킨을 만들고 있어요!</p>
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
            <button onClick={handleGenerate} disabled={isLoading} className="generate-btn">
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
            <label htmlFor="hair-source">헤어스타일 표현</label>
            <select
              id="hair-source"
              aria-describedby="hair-source-help"
              value={hairSource}
              onChange={(e) => setHairSource(e.target.value)}
            >
              <option value="mask">사진 속 머리 모양 반영</option>
              <option value="rule">머리 길이에 맞춘 기본 모양</option>
            </select>
          </div>
          <p id="hair-source-help" className="config-help">사진에서 머리 윤곽을 찾아 반영하거나, 추정한 머리 길이에 맞춰 단순하게 그려요. 윤곽을 찾지 못하면 기본 모양을 사용해요.</p>
          <div className="config-row">
            <label htmlFor="hair-symmetry">머리 좌우 모양</label>
            <select
              id="hair-symmetry"
              aria-describedby="hair-symmetry-help"
              value={hairSymmetry}
              onChange={(e) => setHairSymmetry(e.target.value)}
            >
              <option value="symmetrized">좌우를 대칭으로 정리</option>
              <option value="raw">사진의 좌우 차이 유지</option>
            </select>
          </div>
          <p id="hair-symmetry-help" className="config-help">사진의 머리 윤곽을 사용할 때 적용돼요. 대칭으로 정리하거나 사진에서 감지한 좌우 차이를 남길 수 있어요.</p>
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

        {previewOpen && skins.length > 0 && (
          <SkinPreview skins={skins} onClose={() => setPreviewOpen(false)} />
        )}

        {skins.length > 0 && !previewOpen && (
          <div className="result-section">
            <h2>생성된 64×64 스킨 후보 {skins.length}종</h2>
            <button type="button" className="edit-btn" onClick={() => setPreviewOpen(true)}>미리보기 다시 열기</button>
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
                  <a href={inputPhoto} download="input_photo.png" className="download-btn">
                    사진 다운로드
                  </a>
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
                    <button className="edit-btn" onClick={() => setEditorItem(skin)}>
                      스킨 편집 ✏️
                    </button>
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
