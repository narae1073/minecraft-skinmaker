import React, { useMemo, useRef } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import { characterGeometries } from '../skinModel';

// 지오메트리/UV rect 는 skinModel.js 가 단일 소스다 (QA 렌더 하네스와 공유).
function MinecraftCharacter({ skinUrl, model = 'classic' }) {
  const groupRef = useRef();
  const texture = useLoader(THREE.TextureLoader, skinUrl);

  // 64x64 픽셀이 흐려지지 않게 선명도 유지 — 훅 반환값을 직접 수정하지 않고 복제한다.
  const tex = useMemo(() => {
    const t = texture.clone();
    t.magFilter = THREE.NearestFilter;
    t.minFilter = THREE.NearestFilter;
    t.colorSpace = THREE.SRGBColorSpace;
    t.needsUpdate = true;
    return t;
  }, [texture]);

  const { armX, geos } = useMemo(() => characterGeometries(model), [model]);
  const mat = useMemo(() => new THREE.MeshStandardMaterial({
    map: tex, transparent: true, alphaTest: 0.5,
  }), [tex]);

  useFrame((state, delta) => {
    groupRef.current.rotation.y += delta * 0.5; // 자동 회전
  });

  return (
    <group ref={groupRef} position={[0, -2, 0]}>
      <mesh position={[0, 3.5, 0]} geometry={geos.head} material={mat} />
      <mesh position={[0, 3.5, 0]} geometry={geos.head2} material={mat} />
      <mesh position={[0, 2.25, 0]} geometry={geos.body} material={mat} />
      <mesh position={[0, 2.25, 0]} geometry={geos.body2} material={mat} />
      <mesh position={[-armX, 2.25, 0]} geometry={geos.larm} material={mat} />
      <mesh position={[-armX, 2.25, 0]} geometry={geos.larm2} material={mat} />
      <mesh position={[armX, 2.25, 0]} geometry={geos.arm} material={mat} />
      <mesh position={[armX, 2.25, 0]} geometry={geos.arm2} material={mat} />
      <mesh position={[-0.25, 0.75, 0]} geometry={geos.lleg} material={mat} />
      <mesh position={[-0.25, 0.75, 0]} geometry={geos.lleg2} material={mat} />
      <mesh position={[0.25, 0.75, 0]} geometry={geos.leg} material={mat} />
      <mesh position={[0.25, 0.75, 0]} geometry={geos.leg2} material={mat} />
    </group>
  );
}

export default function Skin3DViewer({ skinUrl, model = 'classic', width = 200, height = 300 }) {
  if (!skinUrl) return <div style={{ width, height, background: '#e2e8f0' }} />;

  return (
    <div style={{ width: `${width}px`, height: `${height}px`, background: '#e2e8f0', borderRadius: '8px' }}>
      <Canvas camera={{ position: [0, 2, 5], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 10, 5]} intensity={1.2} />
        <React.Suspense fallback={null}>
          <MinecraftCharacter skinUrl={skinUrl} model={model} />
        </React.Suspense>
        <OrbitControls enableZoom={true} enablePan={false} />
      </Canvas>
    </div>
  );
}
