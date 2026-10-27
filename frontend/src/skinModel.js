import * as THREE from 'three';

// 64x64 아틀라스 rect → UV. skinmaker/format.py classic 배치가 정본이다.
// rect: [x, y, w, h] 픽셀. TextureLoader flipY 기본값 기준.
export const S = 64;
export function rectUV([x, y, w, h]) {
  return [x / S, 1 - (y + h) / S, (x + w) / S, 1 - y / S];
}

// three.js BoxGeometry 면 순서: px, nx, py, ny, pz, nz. 면당 UV 4개.
export function boxWithUV(w, h, d, faces) {
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
// L2(오버레이) rect: 레이어 0 rect + 오프셋 (classic: 헤드 +32,0 / 몸·팔·다리 +0,16)
export function shiftFaces(faces, dx, dy) {
  return Object.fromEntries(
    Object.entries(faces).map(([k, [x, y, w, h]]) => [k, [x + dx, y + dy, w, h]]),
  );
}
const HEAD2 = shiftFaces(HEAD, 32, 0);
const ARM = {
  px: [48, 20, 4, 12], nx: [40, 20, 4, 12], py: [44, 16, 4, 4],
  ny: [48, 16, 4, 4], pz: [44, 20, 4, 12], nz: [52, 20, 4, 12],
};
const LEG = {
  px: [8, 20, 4, 12], nx: [0, 20, 4, 12], py: [4, 16, 4, 4],
  ny: [8, 16, 4, 4], pz: [4, 20, 4, 12], nz: [12, 20, 4, 12],
};
// 좌측 팔다리는 자기 region을 쓴다 (format.py l_arm (32,48), l_leg (16,48)).
// 기존엔 우측 rect를 재사용해 좌우 노이즈가 같아 보였다 (사용자 지적 2026-10-13).
const LARM = {
  px: [40, 52, 4, 12], nx: [32, 52, 4, 12], py: [36, 48, 4, 4],
  ny: [40, 48, 4, 4], pz: [36, 52, 4, 12], nz: [44, 52, 4, 12],
};
const LLEG = {
  px: [24, 52, 4, 12], nx: [16, 52, 4, 12], py: [20, 48, 4, 4],
  ny: [24, 48, 4, 4], pz: [20, 52, 4, 12], nz: [28, 52, 4, 12],
};
const BODY2 = shiftFaces(BODY, 0, 16);
const ARM2 = shiftFaces(ARM, 0, 16);
const LARM2 = shiftFaces(LARM, 16, 0);   // l_arm (32,48) -> overlay (48,48)
const LEG2 = shiftFaces(LEG, 0, 16);
const LLEG2 = shiftFaces(LLEG, -16, 0);  // l_leg (16,48) -> overlay (0,48)

// slim: 팔 폭 3px (classic 4px). 몸통·머리·다리는 동일하고 L2 오프셋 규칙도 같다.
const SLIM_ARM = {
  px: [47, 20, 4, 12], nx: [40, 20, 4, 12], py: [44, 16, 3, 4],
  ny: [47, 16, 3, 4], pz: [44, 20, 3, 12], nz: [51, 20, 3, 12],
};
const SLIM_LARM = {
  px: [39, 52, 4, 12], nx: [32, 52, 4, 12], py: [36, 48, 3, 4],
  ny: [39, 48, 3, 4], pz: [36, 52, 3, 12], nz: [43, 52, 3, 12],
};
const SLIM_ARM2 = shiftFaces(SLIM_ARM, 0, 16);
const SLIM_LARM2 = shiftFaces(SLIM_LARM, 16, 0);

// 3D 뷰어(Skin3DViewer)와 QA 렌더 하네스(frontend/qa)가 같은 지오메트리를 쓴다.
// 반환값: { slim, armX, geos } — geos 는 레이어0/레이어1(L2) 박스 12개.
export function characterGeometries(model = 'classic') {
  const slim = model === 'slim';
  const armW = slim ? 0.375 : 0.5;
  const armX = slim ? 0.6875 : 0.75;
  const geos = {
    head: boxWithUV(1, 1, 1, HEAD),
    body: boxWithUV(1, 1.5, 0.5, BODY),
    arm: boxWithUV(armW, 1.5, 0.5, slim ? SLIM_ARM : ARM),
    larm: boxWithUV(armW, 1.5, 0.5, slim ? SLIM_LARM : LARM),
    leg: boxWithUV(0.5, 1.5, 0.5, LEG),
    lleg: boxWithUV(0.5, 1.5, 0.5, LLEG),
    // L2 오버레이: 반 픽셀(0.0625 unit) 두껍게
    head2: boxWithUV(1.0625, 1.0625, 1.0625, HEAD2),
    body2: boxWithUV(1.0625, 1.5625, 0.5625, BODY2),
    arm2: boxWithUV(armW + 0.0625, 1.5625, 0.5625, slim ? SLIM_ARM2 : ARM2),
    larm2: boxWithUV(armW + 0.0625, 1.5625, 0.5625, slim ? SLIM_LARM2 : LARM2),
    leg2: boxWithUV(0.5625, 1.5625, 0.5625, LEG2),
    lleg2: boxWithUV(0.5625, 1.5625, 0.5625, LLEG2),
  };
  return { slim, armX, geos };
}
