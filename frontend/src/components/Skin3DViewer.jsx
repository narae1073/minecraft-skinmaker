import React, { useRef } from 'react';
import { Canvas, useFrame, useLoader } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';

function MinecraftCharacter({ skinUrl }) {
  const groupRef = useRef();
  const texture = useLoader(THREE.TextureLoader, skinUrl);
  
  // 64x64 픽셀이 흐려지지 않게 선명도 유지
  texture.magFilter = THREE.NearestFilter;
  texture.minFilter = THREE.NearestFilter;
  texture.colorSpace = THREE.SRGBColorSpace;

  useFrame((state, delta) => {
    groupRef.current.rotation.y += delta * 0.5; // 자동 회전
  });

  return (
    <group ref={groupRef} position={[0, -0.5, 0]}>
      {/* 머리 */}
      <mesh position={[0, 1.5, 0]}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial map={texture} />
      </mesh>
      {/* 몸통 */}
      <mesh position={[0, 0.25, 0]}>
        <boxGeometry args={[1, 1.5, 0.5]} />
        <meshStandardMaterial map={texture} />
      </mesh>
      {/* 팔/다리는 이 아래에 mesh를 추가로 구현하여 확장합니다. */}
    </group>
  );
}

export default function Skin3DViewer({ skinUrl }) {
  if (!skinUrl) return <div style={{ width: 200, height: 300, background: '#e2e8f0' }} />;

  return (
    <div style={{ width: '200px', height: '300px', background: '#e2e8f0', borderRadius: '8px' }}>
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