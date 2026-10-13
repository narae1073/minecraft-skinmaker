import React, { useState } from 'react';
import Skin3DViewer from './components/Skin3DViewer';
import SkinEditor from './components/SkinEditor';
import CategoryPanel from './components/CategoryPanel';
import StepsPanel from './components/StepsPanel';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [fileError, setFileError] = useState(false);
  const [serverError, setServerError] = useState('');
  const [skins, setSkins] = useState([]); // 현재 결과: {url, flatUrl} 쌍 배열
  const [inputPhoto, setInputPhoto] = useState(null);
  const [editorItem, setEditorItem] = useState(null); // SkinEditor 모달 대상 ({url, flatUrl})
  const [noiseLevel, setNoiseLevel] = useState(50); // 노이즈 세기 % (기본 50 — 사용자 결정 2026-10-13)
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
    setSkins([]);
    setInputPhoto(null);
    setServerError('');
    setCatInfo(null);
    setSteps(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('noise_level', String(noiseLevel / 100));

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
        const pairs = (data.data.skins || []).map((url, i) => ({
          url,
          flatUrl: (data.data.skins_flat || [])[i] || null,
          varied: (data.data.candidates || [])[i]?.varied || "",
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
        <h1>마인크래프트 세계로 들어가보자!</h1>
        <p>당신의 전신 사진을 첨부해주세요!</p>
        
        <div className="upload-section">
          <input type="file" accept="image/jpeg, image/png" onChange={handleFileChange} />
          <div className="noise-slider-row" title="0% = 노이즈 없음">
            <label htmlFor="noise-level">노이즈</label>
            <input
              id="noise-level"
              type="range"
              min="0"
              max="100"
              step="5"
              value={noiseLevel}
              onChange={(e) => setNoiseLevel(Number(e.target.value))}
            />
            <span className="noise-readout">{noiseLevel}%</span>
          </div>
          <button onClick={handleGenerate} disabled={isLoading} className="generate-btn">
            {isLoading ? '생성 중...' : '스킨 변환하기'}
          </button>
        </div>

        {skins.length > 0 && (
          <div className="result-section">
            <h2>생성된 64×64 스킨 후보 {skins.length}종</h2>
            <p className="compare-hint">원본 사진을 왼쪽에 두고 스킨을 비교해보세요 (3D 뷰어에서 회전도 가능)</p>
            <div className="analysis-row">
              <CategoryPanel attributes={catInfo?.attributes} noiseLevel={catInfo?.noiseLevel} />
              <StepsPanel steps={steps} />
            </div>
            <div className="compare-grid">
              {inputPhoto && (
                <div className="skin-card input-card">
                  <h3>원본 사진</h3>
                  <img
                    src={inputPhoto}
                    alt="입력 사진"
                    className="input-photo"
                  />
                  <a href={inputPhoto} download={`input_${Date.now()}.png`} className="download-btn">
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
                  <Skin3DViewer skinUrl={skin.url} />
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
          </div>
        )}

        {editorItem && (
          <SkinEditor skin={editorItem} steps={steps} onClose={() => setEditorItem(null)} />
        )}

        <footer className="footer">
          &copy; 2026 몬태규. All rights reserved.
        </footer>
      </div>
    </>
  );
}

export default App;