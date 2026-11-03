import * as THREE from 'three';
import { OrbitControls } from 'three/addons/OrbitControls.js';

// UV rects are ported from frontend/src/skinModel.js (classic layout) so the
// editor viewer and the production viewer agree on the 64x64 atlas.
const S = 64;
const rectUV = ([x, y, w, h]) => [x / S, 1 - (y + h) / S, (x + w) / S, 1 - y / S];
const shiftFaces = (faces, dx, dy) => Object.fromEntries(
  Object.entries(faces).map(([k, [x, y, w, h]]) => [k, [x + dx, y + dy, w, h]]),
);

function boxWithUV(w, h, d, faces) {
  const geo = new THREE.BoxGeometry(w, h, d);
  const uv = geo.attributes.uv;
  const order = ['px', 'nx', 'py', 'ny', 'pz', 'nz'];
  order.forEach((key, i) => {
    const [u0, v0, u1, v1] = rectUV(faces[key]);
    const [top, bot] = key === 'ny' ? [v0, v1] : [v1, v0];
    uv.setXY(i * 4 + 0, u0, top);
    uv.setXY(i * 4 + 1, u1, top);
    uv.setXY(i * 4 + 2, u0, bot);
    uv.setXY(i * 4 + 3, u1, bot);
  });
  uv.needsUpdate = true;
  return geo;
}

const HEAD = { px: [16, 8, 8, 8], nx: [0, 8, 8, 8], py: [8, 0, 8, 8], ny: [16, 0, 8, 8], pz: [8, 8, 8, 8], nz: [24, 8, 8, 8] };
const BODY = { px: [28, 20, 4, 12], nx: [16, 20, 4, 12], py: [20, 16, 8, 4], ny: [28, 16, 8, 4], pz: [20, 20, 8, 12], nz: [32, 20, 8, 12] };
const ARM = { px: [48, 20, 4, 12], nx: [40, 20, 4, 12], py: [44, 16, 4, 4], ny: [48, 16, 4, 4], pz: [44, 20, 4, 12], nz: [52, 20, 4, 12] };
const LEG = { px: [8, 20, 4, 12], nx: [0, 20, 4, 12], py: [4, 16, 4, 4], ny: [8, 16, 4, 4], pz: [4, 20, 4, 12], nz: [12, 20, 4, 12] };
const LARM = { px: [40, 52, 4, 12], nx: [32, 52, 4, 12], py: [36, 48, 4, 4], ny: [40, 48, 4, 4], pz: [36, 52, 4, 12], nz: [44, 52, 4, 12] };
const LLEG = { px: [24, 52, 4, 12], nx: [16, 52, 4, 12], py: [20, 48, 4, 4], ny: [24, 48, 4, 4], pz: [20, 52, 4, 12], nz: [28, 52, 4, 12] };
export const PART_UV = { head: HEAD, body: BODY, r_arm: ARM, l_arm: LARM, r_leg: LEG, l_leg: LLEG };
const FACE_NAME = { px: 'right', nx: 'left', py: 'top', ny: 'bottom', pz: 'front', nz: 'back' };
const HEAD2 = shiftFaces(HEAD, 32, 0);
const BODY2 = shiftFaces(BODY, 0, 16);
const ARM2 = shiftFaces(ARM, 0, 16);
const LARM2 = shiftFaces(LARM, 16, 0);
const LEG2 = shiftFaces(LEG, 0, 16);
const LLEG2 = shiftFaces(LLEG, -16, 0);
export const PART_UV2 = { head: HEAD2, body: BODY2, r_arm: ARM2, l_arm: LARM2, r_leg: LEG2, l_leg: LLEG2 };

// Slim model: head/body/legs share the classic rects; arm width is 3px
// (right/left faces stay 4px). Mirrors skinmaker/format.py get_layout("slim").
const SLIM_ARM = { px: [47, 20, 4, 12], nx: [40, 20, 4, 12], py: [44, 16, 3, 4], ny: [47, 16, 3, 4], pz: [44, 20, 3, 12], nz: [51, 20, 3, 12] };
const SLIM_LARM = { px: [39, 52, 4, 12], nx: [32, 52, 4, 12], py: [36, 48, 3, 4], ny: [39, 48, 3, 4], pz: [36, 52, 3, 12], nz: [43, 52, 3, 12] };
export const PART_UV_SLIM = { head: HEAD, body: BODY, r_arm: SLIM_ARM, l_arm: SLIM_LARM, r_leg: LEG, l_leg: LLEG };
const SLIM_ARM2 = shiftFaces(SLIM_ARM, 0, 16);
const SLIM_LARM2 = shiftFaces(SLIM_LARM, 16, 0);
export const PART_UV2_SLIM = { head: HEAD2, body: BODY2, r_arm: SLIM_ARM2, l_arm: SLIM_LARM2, r_leg: LEG2, l_leg: LLEG2 };

export function initViewer(container) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.style.display = 'block';
  renderer.domElement.style.width = '100%';
  renderer.domElement.style.height = '100%';
  renderer.domElement.addEventListener('contextmenu', (e) => e.preventDefault());
  container.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#eef1f4');
  const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
  camera.position.set(0, 2.2, 6.5);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enablePan = false;
  controls.enableDamping = true;
  // Left-drag paints (app.js); right-drag orbits. No left orbit.
  controls.mouseButtons = { LEFT: null, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
  controls.touches = { ONE: null, TWO: THREE.TOUCH.DOLLY_ROTATE };
  controls.dampingFactor = 0.08;
  controls.target.set(0, 0, 0);

  scene.add(new THREE.AmbientLight(0xffffff, 1.1));
  const key = new THREE.DirectionalLight(0xffffff, 1.8); key.position.set(4, 8, 6); scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.7); fill.position.set(-4, 4, -6); scene.add(fill);

  const material = new THREE.MeshStandardMaterial({ transparent: true, alphaTest: 0.5 });
  const group = new THREE.Group();
  group.position.set(0, -2, 0);
  scene.add(group);
  const geos = {
    head: boxWithUV(1, 1, 1, HEAD),
    head2: boxWithUV(1.0625, 1.0625, 1.0625, HEAD2),
    body: boxWithUV(1, 1.5, 0.5, BODY),
    body2: boxWithUV(1.0625, 1.5625, 0.5625, BODY2),
    arm: boxWithUV(0.5, 1.5, 0.5, ARM),
    arm2: boxWithUV(0.5625, 1.5625, 0.5625, ARM2),
    larm: boxWithUV(0.5, 1.5, 0.5, LARM),
    larm2: boxWithUV(0.5625, 1.5625, 0.5625, LARM2),
    slimArm: boxWithUV(0.375, 1.5, 0.5, SLIM_ARM),
    slimArm2: boxWithUV(0.4375, 1.5625, 0.5625, SLIM_ARM2),
    slimLarm: boxWithUV(0.375, 1.5, 0.5, SLIM_LARM),
    slimLarm2: boxWithUV(0.4375, 1.5625, 0.5625, SLIM_LARM2),
    leg: boxWithUV(0.5, 1.5, 0.5, LEG),
    leg2: boxWithUV(0.5625, 1.5625, 0.5625, LEG2),
    lleg: boxWithUV(0.5, 1.5, 0.5, LLEG),
    lleg2: boxWithUV(0.5625, 1.5625, 0.5625, LLEG2),
  };
  const meshes = {};
  const add = (geo, x, y, z, name) => {
    const mesh = new THREE.Mesh(geo, material);
    mesh.position.set(x, y, z);
    mesh.name = name;
    group.add(mesh);
    meshes[name] = mesh;
    return mesh;
  };
  add(geos.head, 0, 3.5, 0, 'head'); add(geos.head2, 0, 3.5, 0, 'head2');
  add(geos.body, 0, 2.25, 0, 'body'); add(geos.body2, 0, 2.25, 0, 'body2');
  add(geos.larm, -0.75, 2.25, 0, 'larm'); add(geos.larm2, -0.75, 2.25, 0, 'larm2');
  add(geos.arm, 0.75, 2.25, 0, 'arm'); add(geos.arm2, 0.75, 2.25, 0, 'arm2');
  add(geos.lleg, -0.25, 0.75, 0, 'lleg'); add(geos.lleg2, -0.25, 0.75, 0, 'lleg2');
  add(geos.leg, 0.25, 0.75, 0, 'leg'); add(geos.leg2, 0.25, 0.75, 0, 'leg2');

  let texture = null;
  let loadToken = 0;
  function setSkin(url) {
    const token = ++loadToken;
    new THREE.TextureLoader().load(url, (t) => {
      if (token !== loadToken) { t.dispose(); return; }
      t.magFilter = THREE.NearestFilter;
      t.minFilter = THREE.NearestFilter;
      t.colorSpace = THREE.SRGBColorSpace;
      t.needsUpdate = true;
      if (texture) texture.dispose();
      texture = t;
      material.map = t;
      material.needsUpdate = true;
    });
  }

  function resize() {
    const w = container.clientWidth || 520;
    const h = container.clientHeight || 620;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener('resize', resize);
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(resize).observe(container);
  resize();

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const MASK_FACE = {
    px: 'head.right', nx: 'head.left', py: 'head.top',
    pz: 'head.front', nz: 'head.back', ny: 'head.bottom',
  };

  const PART_MESH = {
    head: ['head', 'head2'], body: ['body', 'body2'],
    r_arm: ['arm', 'arm2'], l_arm: ['larm', 'larm2'],
    r_leg: ['leg', 'leg2'], l_leg: ['lleg', 'lleg2'],
  };
  let activeUV = PART_UV;
  let activeUV2 = PART_UV2;

  function setModel(model) {
    const slim = model === 'slim';
    meshes.arm.geometry = slim ? geos.slimArm : geos.arm;
    meshes.arm2.geometry = slim ? geos.slimArm2 : geos.arm2;
    meshes.larm.geometry = slim ? geos.slimLarm : geos.larm;
    meshes.larm2.geometry = slim ? geos.slimLarm2 : geos.larm2;
    // L1 and L2 arms share one x so the overlay stays concentric.
    const armX = slim ? 0.6875 : 0.75;
    meshes.arm.position.x = armX;
    meshes.arm2.position.x = armX;
    meshes.larm.position.x = -armX;
    meshes.larm2.position.x = -armX;
    activeUV = slim ? PART_UV_SLIM : PART_UV;
    activeUV2 = slim ? PART_UV2_SLIM : PART_UV2;
  }

  function pick(part, layer, clientX, clientY) {
    const rect = renderer.domElement.getBoundingClientRect();
    if (clientX < rect.left || clientX > rect.right || clientY < rect.top || clientY > rect.bottom) return null;
    pointer.set(((clientX - rect.left) / rect.width) * 2 - 1, -((clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    const names = PART_MESH[part];
    if (!names) return null;
    const meshName = layer === 'L1' ? names[0] : names[1];
    const mesh = meshes[meshName];
    if (!mesh) return null;
    const hits = raycaster.intersectObject(mesh, false);
    if (!hits.length) return null;
    const hit = hits[0];
    const n = hit.face.normal;
    const ax = Math.abs(n.x), ay = Math.abs(n.y), az = Math.abs(n.z);
    const key = ax >= ay && ax >= az ? (n.x > 0 ? 'px' : 'nx')
      : ay >= az ? (n.y > 0 ? 'py' : 'ny') : (n.z > 0 ? 'pz' : 'nz');
    const faceName = FACE_NAME[key];
    const faceRect = (layer === 'L1' ? activeUV : activeUV2)[part][key];
    const px = Math.floor(hit.uv.x * S);
    const py = Math.floor((1 - hit.uv.y) * S);
    const u = px - faceRect[0], v = py - faceRect[1];
    if (u < 0 || u >= faceRect[2] || v < 0 || v >= faceRect[3]) return null;
    return { part, face: `${part}.${faceName}`, u, v };
  }

  function pickHead(clientX, clientY, layer) {
    return pick('head', layer, clientX, clientY);
  }

  function setEditableLayer(layers) {
    const selected = Array.isArray(layers) ? layers : [layers];
    const showL2 = selected.includes('L2');
    for (const name of ['head2', 'body2', 'arm2', 'larm2', 'leg2', 'lleg2']) {
      if (meshes[name]) meshes[name].visible = showL2;
    }
  }

  function projectPoint(x, y, z) {
    const v = new THREE.Vector3(x, y, z).project(camera);
    const r = renderer.domElement.getBoundingClientRect();
    return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height };
  }

  function projectHead() { return projectPoint(0, 1.5, 0); }

  animate();
  setModel('classic');
  return { setSkin, setModel, controls, camera, resize, pick, pickHead, setEditableLayer, projectHead, projectPoint, meshes };
}
