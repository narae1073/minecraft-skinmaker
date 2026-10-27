import * as THREE from 'three';
import { characterGeometries } from '/frontend/src/skinModel.js';

// Headless QA render harness. Camera is a weak-perspective (near-orthographic)
// camera so the front and back shots stay directly comparable.
// Driven by skinmaker/qarender.py; all parameters arrive via the query string.

const params = new URLSearchParams(window.location.search);
const num = (key, fallback) => {
  const raw = params.get(key);
  return raw === null ? fallback : Number(raw);
};

const width = num('width', 512);
const height = num('height', 768);
const yaw = num('yaw', 24);
const pitch = num('pitch', 30);
const fov = num('fov', 12);
const distance = num('distance', 24);
const model = params.get('model') || 'classic';
const skinUrl = params.get('skin');
if (!skinUrl) throw new Error('missing skin query parameter');

const renderer = new THREE.WebGLRenderer({
  antialias: true,
  preserveDrawingBuffer: true,
  alpha: false,
});
renderer.setPixelRatio(1);
renderer.setSize(width, height);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0xe2e8f0, 1);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();

const cam = new THREE.PerspectiveCamera(fov, width / height, 0.1, 500);
const yawRad = THREE.MathUtils.degToRad(yaw);
const pitchRad = THREE.MathUtils.degToRad(pitch);
cam.position.set(
  distance * Math.sin(yawRad) * Math.cos(pitchRad),
  distance * Math.sin(pitchRad),
  distance * Math.cos(yawRad) * Math.cos(pitchRad),
);
cam.up.set(0, 1, 0);
cam.lookAt(0, 0, 0);

// Same lights as the interactive viewer (Skin3DViewer.jsx).
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.2);
sun.position.set(5, 10, 5);
scene.add(sun);

const texture = await new THREE.TextureLoader().loadAsync(skinUrl);
texture.magFilter = THREE.NearestFilter;
texture.minFilter = THREE.NearestFilter;
texture.colorSpace = THREE.SRGBColorSpace;
texture.needsUpdate = true;

// alphaTest matches the viewer: transparent L2 cells are discarded, opaque
// L2 cells draw over L1 (the geometry is inflated by half a texel).
const material = new THREE.MeshStandardMaterial({
  map: texture,
  transparent: true,
  alphaTest: 0.5,
});

const { armX, geos } = characterGeometries(model);
const group = new THREE.Group();
group.position.set(0, -2, 0);
const add = (geo, x, y, z) => {
  const mesh = new THREE.Mesh(geo, material);
  mesh.position.set(x, y, z);
  group.add(mesh);
};
add(geos.head, 0, 3.5, 0);
add(geos.head2, 0, 3.5, 0);
add(geos.body, 0, 2.25, 0);
add(geos.body2, 0, 2.25, 0);
add(geos.larm, -armX, 2.25, 0);
add(geos.larm2, -armX, 2.25, 0);
add(geos.arm, armX, 2.25, 0);
add(geos.arm2, armX, 2.25, 0);
add(geos.lleg, -0.25, 0.75, 0);
add(geos.lleg2, -0.25, 0.75, 0);
add(geos.leg, 0.25, 0.75, 0);
add(geos.leg2, 0.25, 0.75, 0);
scene.add(group);

renderer.render(scene, cam);

window.qaRenderMeta = {
  yaw,
  pitch,
  fov,
  distance,
  model,
  camera: cam.position.toArray(),
  target: [0, 0, 0],
};
document.title = 'QA_READY';
