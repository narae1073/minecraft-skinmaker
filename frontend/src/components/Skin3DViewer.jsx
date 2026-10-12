import React, { useMemo, useRef } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

// 64x64 아틀라스 rect → UV. skinmaker/format.py classic 배치가 정본이다.
// rect: [x, y, w, h] 픽셀. TextureLoader flipY 기본값 기준.
const S = 64;
function rectUV([x, y, w, h]) {
  return [x / S, 1 - (y + h) / S, (x + w) / S, 1 - y / S];
}

// three.js BoxGeometry 면 순서: px, nx, py, ny, pz, nz. 면당 UV 4개.
function boxWithUV(w, h, d, faces) {
  const geo = new THREE.BoxGeometry(w, h, d);
  const uv = geo.attributes.uv;
  const order = ['px', 'nx', 'py', 'ny', 'pz', 'nz'];
  order.forEach((key, i) => {
    const [u0, v0, u1, v1] = rectUV(faces[key]);
    uv.setXY(i * 4 + 0, u0, v1);
    uv.setXY(i * 4 + 1, u1, v1);
    uv.setXY(i * 4 + 2, u0, v0);
    uv.setXY(i * 4 + 3, u1, v0);
  });
  uv.needsUpdate = true;
  return geo;
}

// classic 레이어 0 rect. 좌우 대칭 스킨이라 좌측 팔다리는 우측 rect 재사용.
const HEAD = {
  px: [16, 8, 8, 8], nx: [0, 8, 8, 8], py: [8, 0, 8, 8],
  ny: [16, 0, 8, 8], pz: [8, 8, 8, 8], nz: [24, 8, 8, 8],
};
const BODY = {
  px: [28, 20, 4, 12], nx: [16, 20, 4, 12], py: [20, 16, 8, 4],
  ny: [28, 16, 8, 4], pz: [20, 20, 8, 12], nz: [32, 20, 8, 12],
};
const ARM = {
  px: [48, 20, 4, 12], nx: [40, 20, 4, 12], py: [44, 16, 4, 4],
  ny: [48, 16, 4, 4], pz: [44, 20, 4, 12], nz: [52, 20, 4, 12],
};
const LEG = {
  px: [8, 20, 4, 12], nx: [0, 20, 4, 12], py: [4, 16, 4, 4],
  ny: [8, 16, 4, 4], pz: [4, 20, 4, 12], nz: [12, 20, 4, 12],
};

function MinecraftCharacter({ skinUrl }) {
  const groupRef = useRef();
  const texture = useLoader(THREE.TextureLoader, skinUrl);

  // 64x64 픽셀이 흐려지지 않게 선명도 유지
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.colorSpace = THREE.SRGBColorSpace;

  const geos = useMemo(() => ({
    head: boxWithUV(1, 1, 1, HEAD),
    body: boxWithUV(1, 1.5, 0.5, BODY),
    arm: boxWithUV(0.5, 1.5, 0.5, ARM),
    leg: boxWithUV(0.5, 1.5, 0.5, LEG),
  }), []);
  const mat = useMemo(() => new THREE.MeshStandardMaterial({
    map: texture, transparent: true, alphaTest: 0.5,
  }), [texture]);

  useFrame((state, delta) => {
    groupRef.current.rotation.y += delta * 0.5; // 자동 회전
  });

  return (
    <group ref={groupRef} position={[0, -2, 0]}>
      <mesh position={[0, 3.5, 0]} geometry={geos.head} material={mat} />
      <mesh position={[0, 2.25, 0]} geometry={geos.body} material={mat} />
      <mesh position={[-0.75, 2.25, 0]} geometry={geos.arm} material={mat} />
      <mesh position={[0.75, 2.25, 0]} geometry={geos.arm} material={mat} />
      <mesh position={[-0.25, 0.75, 0]} geometry={geos.leg} material={mat} />
      <mesh position={[0.25, 0.75, 0]} geometry={geos.leg} material={mat} />
    </group>
  );
}

export default function Skin3DViewer({ skinUrl, width = 200, height = 300 }) {
  if (!skinUrl) return <div style={{ width, height, background: '#e2e8f0' }} />;

  return (
    <div style={{ width: `${width}px`, height: `${height}px`, background: '#e2e8f0', borderRadius: '8px' }}>
      <Canvas camera={{ position: [0, 2, 5], fov: 50 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[5, 10, 5]} intensity={1.2} />
        <React.Suspense fallback={null}>
          <MinecraftCharacter skinUrl={skinUrl} />
        </React.Suspense>
        <OrbitControls enableZoom={true} enablePan={false} />
      </Canvas>
    </div>
  );
}
