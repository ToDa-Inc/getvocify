import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { RoundedBoxGeometry } from "three/examples/jsm/geometries/RoundedBoxGeometry.js";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { SVGLoader } from "three/examples/jsm/loaders/SVGLoader.js";

export type Object3DVariant = "ring" | "hub" | "gauge" | "handset" | "whatsapp" | "briefcase" | "clipboard" | "database";

interface Built {
  update: (t: number, dt: number, pointer: number) => void;
  dispose: () => void;
}

const BEIGE = 0xdbc09a;

const glossyBlack = () =>
  new THREE.MeshPhysicalMaterial({ color: 0x1b1b1d, metalness: 0.35, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.1 });

const lights = (scene: THREE.Scene, shadows: boolean) => {
  const key = new THREE.DirectionalLight(BEIGE, 3.4);
  key.position.set(4, 6, 5);
  if (shadows) {
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.radius = 6;
    Object.assign(key.shadow.camera, { left: -4, right: 4, top: 4, bottom: -4 });
  }
  const rim = new THREE.DirectionalLight(0xffffff, 2.4);
  rim.position.set(-5, 3, -4);
  scene.add(key, rim);
};

/** A ring of glossy black bars that move like a voice, standing on a soft contact shadow. */
const buildRing = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  const BARS = 30;
  const RADIUS = 1.85;
  const FLOOR = -0.62;
  camera.position.set(0, 3.0, 7.4);
  camera.lookAt(0, 0.05, 0);
  lights(scene, true);

  const floor = new THREE.Mesh(new THREE.PlaneGeometry(14, 14), new THREE.ShadowMaterial({ opacity: 0.42 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = FLOOR;
  floor.receiveShadow = true;
  scene.add(floor);

  const geometry = new RoundedBoxGeometry(0.2, 1, 0.2, 5, 0.075);
  const material = glossyBlack();
  const ring = new THREE.Group();
  const bars: THREE.Mesh[] = [];
  for (let i = 0; i < BARS; i++) {
    const a = (i / BARS) * Math.PI * 2;
    const bar = new THREE.Mesh(geometry, material);
    bar.position.set(Math.cos(a) * RADIUS, 0, Math.sin(a) * RADIUS);
    bar.rotation.y = -a;
    bar.castShadow = true;
    ring.add(bar);
    bars.push(bar);
  }
  scene.add(ring);

  let smooth = 0;
  return {
    update: (t, _dt, pointer) => {
      bars.forEach((bar, i) => {
        const wave = 0.5 + 0.5 * Math.sin(t * 1.5 + i * 0.62);
        const swell = 0.55 + 0.45 * Math.sin(t * 0.55 + i * 0.21 + 1.3);
        const h = 0.35 + 1.45 * wave * swell;
        bar.scale.y = h;
        bar.position.y = FLOOR + h / 2;
      });
      smooth += (pointer - smooth) * 0.05;
      ring.rotation.y = t * 0.16 + smooth * 0.6;
    },
    dispose: () => {
      geometry.dispose();
      material.dispose();
      floor.geometry.dispose();
      (floor.material as THREE.Material).dispose();
    },
  };
};

/** A warm metal core with glossy black satellites on tilted orbits: one connection, many tools. */
const buildHub = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 2.0, 10.6);
  camera.lookAt(0, 0, 0);
  lights(scene, false);

  const disposables: { dispose: () => void }[] = [];
  const track = <T extends { dispose: () => void }>(o: T) => {
    disposables.push(o);
    return o;
  };

  const metal = track(new THREE.MeshPhysicalMaterial({ color: 0xd2b184, metalness: 0.5, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.08 }));
  const black = track(glossyBlack());
  const line = track(new THREE.MeshBasicMaterial({ color: BEIGE, transparent: true, opacity: 0.32 }));

  const hub = new THREE.Group();
  const core = new THREE.Mesh(track(new THREE.SphereGeometry(0.62, 64, 64)), metal);
  hub.add(core);

  const orbits = [
    { r: 1.5, tilt: 0.35, speed: 0.55, size: 0.34 },
    { r: 2.05, tilt: -0.6, speed: -0.38, size: 0.3 },
    { r: 2.65, tilt: 0.95, speed: 0.27, size: 0.26 },
  ];
  const spinners = orbits.map((o, i) => {
    const tilt = new THREE.Group();
    tilt.rotation.z = o.tilt;
    tilt.rotation.x = i * 0.4;
    const track3 = new THREE.Mesh(track(new THREE.TorusGeometry(o.r, 0.008, 8, 180)), line);
    track3.rotation.x = Math.PI / 2;
    tilt.add(track3);
    const spin = new THREE.Group();
    const sat = new THREE.Mesh(track(new RoundedBoxGeometry(o.size, o.size, o.size, 5, o.size * 0.3)), black);
    sat.position.x = o.r;
    spin.add(sat);
    tilt.add(spin);
    hub.add(tilt);
    return { spin, sat, speed: o.speed };
  });
  scene.add(hub);

  let smooth = 0;
  return {
    update: (t, dt, pointer) => {
      spinners.forEach((s, i) => {
        s.spin.rotation.y = t * s.speed + i * 2;
        s.sat.rotation.x += dt * (0.6 + i * 0.2);
        s.sat.rotation.y += dt * 0.5;
      });
      smooth += (pointer - smooth) * 0.05;
      hub.rotation.y = smooth * 0.5;
      hub.rotation.x = 0.18 + Math.sin(t * 0.4) * 0.05;
    },
    dispose: () => disposables.forEach((d) => d.dispose()),
  };
};

/** A 270 degree gauge in glossy metal over a dark track, filling to `value` percent. */
const buildGauge = (scene: THREE.Scene, camera: THREE.PerspectiveCamera, value: number): Built => {
  const SWEEP = Math.PI * 1.5;
  const R = 1;
  const TUBE = 0.17;
  const START = -Math.PI / 4;
  camera.position.set(0, 0, 5.4);
  camera.lookAt(0, 0, 0);
  lights(scene, false);

  const track = new THREE.MeshPhysicalMaterial({ color: 0x242426, metalness: 0.3, roughness: 0.3, clearcoat: 0.8 });
  const fill = new THREE.MeshPhysicalMaterial({ color: 0xd2b184, metalness: 0.45, roughness: 0.34, clearcoat: 1, clearcoatRoughness: 0.08 });
  const TRACK_TUBE = TUBE * 0.82; // thinner than the fill, so the two never share a surface (that z-fights into speckle)
  const capGeometry = new THREE.SphereGeometry(TUBE, 32, 32);
  const trackCapGeometry = new THREE.SphereGeometry(TRACK_TUBE, 32, 32);

  // arcs are drawn counter-clockwise from START, then the group is mirrored so the fill runs clockwise from the bottom left
  const group = new THREE.Group();
  group.scale.x = -1;
  const arc = (sweep: number, material: THREE.Material, tube = TUBE) => {
    const mesh = new THREE.Mesh(new THREE.TorusGeometry(R, tube, 40, 160, Math.max(sweep, 0.001)), material);
    mesh.rotation.z = START;
    return mesh;
  };
  const cap = (angle: number, material: THREE.Material, geometry: THREE.BufferGeometry = capGeometry) => {
    const m = new THREE.Mesh(geometry, material);
    m.position.set(Math.cos(START + angle) * R, Math.sin(START + angle) * R, 0);
    return m;
  };
  group.add(arc(SWEEP, track, TRACK_TUBE), cap(0, track, trackCapGeometry), cap(SWEEP, track, trackCapGeometry));
  let valueArc = arc(0, fill);
  const startCap = cap(0, fill);
  const endCap = cap(0, fill);
  group.add(valueArc, startCap, endCap);
  scene.add(group);

  const target = Math.min(1, Math.max(0, value / 100)) * SWEEP;
  let shown = -1;
  let smooth = 0;
  return {
    update: (t, _dt, pointer) => {
      const progress = Math.min(1, t / 1.4);
      const eased = 1 - Math.pow(1 - progress, 3);
      const sweep = target * eased;
      if (Math.abs(sweep - shown) > 0.004) {
        shown = sweep;
        group.remove(valueArc);
        valueArc.geometry.dispose();
        valueArc = arc(sweep, fill);
        group.add(valueArc);
        endCap.position.set(Math.cos(START + sweep) * R, Math.sin(START + sweep) * R, 0);
      }
      smooth += (pointer - smooth) * 0.06;
      group.rotation.y = smooth * 0.5 + Math.sin(t * 0.6) * 0.12;
      group.rotation.x = -0.12 + Math.sin(t * 0.45) * 0.05;
    },
    dispose: () => {
      track.dispose();
      fill.dispose();
      capGeometry.dispose();
      trackCapGeometry.dispose();
      valueArc.geometry.dispose();
      group.children.forEach((c) => {
        if (c !== valueArc && c !== startCap && c !== endCap && (c as THREE.Mesh).geometry !== capGeometry && (c as THREE.Mesh).geometry !== trackCapGeometry) (c as THREE.Mesh).geometry.dispose();
      });
    },
  };
};

const track = (list: { dispose: () => void }[]) => <T extends { dispose: () => void }>(o: T) => {
  list.push(o);
  return o;
};

const addFloor = (scene: THREE.Scene, y: number, list: { dispose: () => void }[]) => {
  const floor = new THREE.Mesh(track(list)(new THREE.PlaneGeometry(14, 14)), track(list)(new THREE.ShadowMaterial({ opacity: 0.4 })));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = y;
  floor.receiveShadow = true;
  scene.add(floor);
  return floor;
};

const castAll = (group: THREE.Object3D) => group.traverse((o) => ((o as THREE.Mesh).isMesh ? ((o as THREE.Mesh).castShadow = true) : undefined));

/** A rounded rectangle with UVs normalised to 0..1, so a canvas texture maps onto it exactly. */
const roundedRect = (w: number, h: number, r: number) => {
  const shape = new THREE.Shape();
  shape.moveTo(-w / 2 + r, -h / 2);
  shape.lineTo(w / 2 - r, -h / 2);
  shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
  shape.lineTo(w / 2, h / 2 - r);
  shape.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
  shape.lineTo(-w / 2 + r, h / 2);
  shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
  shape.lineTo(-w / 2, -h / 2 + r);
  shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);
  const geometry = new THREE.ShapeGeometry(shape, 12);
  const pos = geometry.attributes.position;
  const uv = new Float32Array(pos.count * 2);
  for (let i = 0; i < pos.count; i++) {
    uv[i * 2] = (pos.getX(i) + w / 2) / w;
    uv[i * 2 + 1] = (pos.getY(i) + h / 2) / h;
  }
  geometry.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
  return geometry;
};

const warmMetal = () => new THREE.MeshPhysicalMaterial({ color: 0xd2b184, metalness: 0.5, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.08 });

/** The telephone-handset glyph (Material "call"), extruded: it rings, with sound waves. SDR. */
const HANDSET_PATH = "M20.01 15.38c-1.23 0-2.42-.2-3.53-.56a.977.977 0 0 0-1.01.24l-1.57 1.97c-2.83-1.35-5.48-3.9-6.89-6.83l1.95-1.66c.27-.28.35-.67.24-1.02-.37-1.11-.56-2.3-.56-3.53 0-.54-.45-.99-.99-.99H4.19C3.65 3 3 3.24 3 3.99 3 13.28 10.73 21 20.01 21c.71 0 .99-.63.99-1.18v-3.45c0-.54-.45-.99-.99-.99z";
const buildHandset = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 0, 9.4);
  camera.lookAt(0, 0, 0);
  lights(scene, false);
  const list: { dispose: () => void }[] = [];
  const t = track(list);

  const svg = new SVGLoader().parse(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="${HANDSET_PATH}"/></svg>`);
  const shapes = svg.paths.flatMap((p) => SVGLoader.createShapes(p));
  const geometry = t(new THREE.ExtrudeGeometry(shapes, { depth: 3.2, bevelEnabled: true, bevelThickness: 0.7, bevelSize: 0.55, bevelSegments: 6, curveSegments: 40 }));
  geometry.computeBoundingBox();
  const box = geometry.boundingBox!;
  geometry.translate(-(box.min.x + box.max.x) / 2, -(box.min.y + box.max.y) / 2, -(box.min.z + box.max.z) / 2);

  const body = t(glossyBlack());
  const handset = new THREE.Mesh(geometry, body);
  const SCALE = 0.135;
  handset.scale.set(SCALE, -SCALE, SCALE);

  // sound waves leaving the earpiece
  const waveMaterials: THREE.MeshBasicMaterial[] = [];
  const waves = new THREE.Group();
  [1.15, 1.6, 2.05].forEach((radius) => {
    const material = t(new THREE.MeshBasicMaterial({ color: 0xd2b184, transparent: true, opacity: 0 }));
    waveMaterials.push(material);
    const arc = new THREE.Mesh(t(new THREE.TorusGeometry(radius, 0.045, 12, 64, 1.05)), material);
    arc.rotation.z = Math.PI / 4 - 0.52;
    waves.add(arc);
  });
  waves.position.set(0.95, 0.95, 0);

  const holder = new THREE.Group();
  holder.add(handset, waves);
  scene.add(holder);

  let smooth = 0;
  return {
    update: (time, _dt, pointer) => {
      const ringing = time % 3.4 < 1.1 ? 1 : 0;
      handset.rotation.z = ringing * Math.sin(time * 34) * 0.07;
      waveMaterials.forEach((m, i) => {
        const phase = (time * 1.1 - i * 0.22) % 1;
        m.opacity = 0.65 * Math.max(0, Math.sin(Math.min(phase, 1) * Math.PI));
      });
      smooth += (pointer - smooth) * 0.05;
      holder.rotation.y = smooth * 0.5 + Math.sin(time * 0.55) * 0.45;
      holder.rotation.x = Math.sin(time * 0.45) * 0.08;
      holder.position.y = Math.sin(time * 0.9) * 0.08;
    },
    dispose: () => list.forEach((d) => d.dispose()),
  };
};

/** The WhatsApp mark, extruded: field reps talk to their CRM over WhatsApp. */
const WHATSAPP_PATH = "M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z";
const buildWhatsApp = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 0, 9.4);
  camera.lookAt(0, 0, 0);
  lights(scene, false);
  const list: { dispose: () => void }[] = [];
  const t = track(list);

  const svg = new SVGLoader().parse(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="${WHATSAPP_PATH}"/></svg>`);
  const shapes = svg.paths.flatMap((p) => SVGLoader.createShapes(p));
  const options = { depth: 2.2, bevelEnabled: true, bevelThickness: 0.55, bevelSize: 0.42, bevelOffset: 0, bevelSegments: 6, curveSegments: 32 };
  const logo = t(new THREE.ExtrudeGeometry(shapes, options));
  logo.computeBoundingBox();
  const box = logo.boundingBox!;
  const cx = (box.min.x + box.max.x) / 2;
  const cy = (box.min.y + box.max.y) / 2;
  const cz = (box.min.z + box.max.z) / 2;
  logo.translate(-cx, -cy, -cz);

  // the handset is a hole in the logo: a white plate behind it shows through
  const outline = new THREE.Shape(shapes[0].extractPoints(32).shape);
  const plate = t(new THREE.ExtrudeGeometry(outline, { depth: 0.4, bevelEnabled: false, curveSegments: 32 }));
  plate.translate(-cx, -cy, 0.5 - cz);

  const green = t(new THREE.MeshPhysicalMaterial({ color: 0x25d366, metalness: 0.1, roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.08 }));
  const white = t(new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.55 }));

  const group = new THREE.Group();
  group.add(new THREE.Mesh(logo, green), new THREE.Mesh(plate, white));
  const SCALE = 0.118;
  group.scale.set(SCALE, -SCALE, SCALE);
  const holder = new THREE.Group();
  holder.add(group);
  scene.add(holder);

  let smooth = 0;
  return {
    update: (time, _dt, pointer) => {
      smooth += (pointer - smooth) * 0.05;
      holder.rotation.y = smooth * 0.5 + Math.sin(time * 0.6) * 0.5;
      holder.rotation.x = Math.sin(time * 0.45) * 0.08;
      holder.position.y = Math.sin(time * 0.9) * 0.1;
    },
    dispose: () => list.forEach((d) => d.dispose()),
  };
};

/** A clipboard with a playbook checklist that ticks itself off: heads of sales. */
const buildClipboard = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 0, 9);
  camera.lookAt(0, 0, 0);
  lights(scene, false);
  const list: { dispose: () => void }[] = [];
  const t = track(list);

  const canvas = document.createElement("canvas");
  canvas.width = 300;
  canvas.height = 420;
  const ctx = canvas.getContext("2d")!;
  const texture = t(new THREE.CanvasTexture(canvas));
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const draw = (time: number) => {
    ctx.fillStyle = "#f6f2ec";
    ctx.fillRect(0, 0, 300, 420);
    ctx.fillStyle = "#cbbfae";
    ctx.beginPath();
    ctx.roundRect(30, 56, 130, 18, 9);
    ctx.fill();
    const done = Math.floor((time * 0.8) % 5);
    for (let i = 0; i < 4; i++) {
      const y = 130 + i * 68;
      const on = i < done;
      ctx.fillStyle = on ? "#c9a56f" : "#e8e1d6";
      ctx.beginPath();
      ctx.arc(52, y, 17, 0, Math.PI * 2);
      ctx.fill();
      if (on) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 4;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(44, y);
        ctx.lineTo(50, y + 6);
        ctx.lineTo(61, y - 6);
        ctx.stroke();
      }
      ctx.fillStyle = "#d9d0c3";
      ctx.beginPath();
      ctx.roundRect(88, y - 12, 150 - (i % 2) * 30, 16, 8);
      ctx.fill();
      ctx.fillStyle = "#e9e3da";
      ctx.beginPath();
      ctx.roundRect(88, y + 9, 100, 9, 4.5);
      ctx.fill();
    }
    texture.needsUpdate = true;
  };
  draw(0);

  const graphite = t(new THREE.MeshPhysicalMaterial({ color: 0x2a2a2d, metalness: 0.3, roughness: 0.3, clearcoat: 0.9 }));
  const metal = t(warmMetal());
  const board = new THREE.Group();
  board.add(new THREE.Mesh(t(new RoundedBoxGeometry(2.35, 3.15, 0.14, 5, 0.13)), graphite));
  const paper = new THREE.Mesh(t(roundedRect(1.95, 2.65, 0.08)), t(new THREE.MeshBasicMaterial({ map: texture, toneMapped: false })));
  paper.position.z = 0.075;
  board.add(paper);
  const clip = new THREE.Mesh(t(new RoundedBoxGeometry(0.85, 0.32, 0.16, 4, 0.08)), metal);
  clip.position.set(0, 1.5, 0.09);
  board.add(clip);
  board.rotation.x = -0.05;
  const holder = new THREE.Group();
  holder.add(board);
  scene.add(holder);

  let smooth = 0;
  let last = 0;
  return {
    update: (time, _dt, pointer) => {
      if (time - last > 0.12) {
        last = time;
        draw(time);
      }
      smooth += (pointer - smooth) * 0.05;
      holder.rotation.y = smooth * 0.5 + Math.sin(time * 0.55) * 0.42;
      holder.rotation.z = Math.sin(time * 0.4) * 0.04;
      holder.position.y = Math.sin(time * 0.9) * 0.09;
    },
    dispose: () => list.forEach((d) => d.dispose()),
  };
};

/** A stack of glossy server discs with warm rings and status lights: the data layer, RevOps. */
const buildDatabase = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 2.6, 8.8);
  camera.lookAt(0, 0.05, 0);
  lights(scene, true);
  const list: { dispose: () => void }[] = [];
  const t = track(list);
  const floor = addFloor(scene, -1.36, list);

  const black = t(glossyBlack());
  const metal = t(warmMetal());
  const lamp = t(new THREE.MeshBasicMaterial({ color: 0xdbc09a }));
  const discGeometry = t(new THREE.CylinderGeometry(1.25, 1.25, 0.62, 72));
  const ringGeometry = t(new THREE.TorusGeometry(1.255, 0.03, 12, 120));
  const lampGeometry = t(new THREE.SphereGeometry(0.055, 16, 16));

  const stack = new THREE.Group();
  const discs: THREE.Group[] = [];
  [-1, 0, 1].forEach((level) => {
    const disc = new THREE.Group();
    disc.position.y = level * 1.0;
    disc.add(new THREE.Mesh(discGeometry, black));
    const ring = new THREE.Mesh(ringGeometry, metal);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = 0.31;
    disc.add(ring);
    [-0.78, -0.62].forEach((x) => {
      const dot = new THREE.Mesh(lampGeometry, lamp);
      dot.position.set(x, 0, 1.255);
      disc.add(dot);
    });
    stack.add(disc);
    discs.push(disc);
  });
  const cap = new THREE.Mesh(t(new THREE.CylinderGeometry(0.95, 0.95, 0.03, 72)), metal);
  cap.position.y = 1.0 + 0.325;
  stack.add(cap);
  castAll(stack);
  const holder = new THREE.Group();
  holder.add(stack);
  holder.rotation.x = 0.1;
  scene.add(holder);

  let smooth = 0;
  return {
    update: (time, _dt, pointer) => {
      discs.forEach((d, i) => {
        d.rotation.y = time * (0.28 + i * 0.12) * (i % 2 ? -1 : 1);
      });
      smooth += (pointer - smooth) * 0.05;
      holder.rotation.y = smooth * 0.5 + Math.sin(time * 0.4) * 0.3;
    },
    dispose: () => {
      list.forEach((d) => d.dispose());
      floor.geometry.dispose();
    },
  };
};

/** A glossy black briefcase with warm metal clasps: the account executive's tool. */
const buildBriefcase = (scene: THREE.Scene, camera: THREE.PerspectiveCamera): Built => {
  camera.position.set(0, 0.5, 8.4);
  camera.lookAt(0, 0.1, 0);
  lights(scene, false);

  const disposables: { dispose: () => void }[] = [];
  const track = <T extends { dispose: () => void }>(o: T) => {
    disposables.push(o);
    return o;
  };
  const body = track(glossyBlack());
  const metal = track(new THREE.MeshPhysicalMaterial({ color: 0xd2b184, metalness: 0.5, roughness: 0.3, clearcoat: 1, clearcoatRoughness: 0.08 }));

  const group = new THREE.Group();
  group.add(new THREE.Mesh(track(new RoundedBoxGeometry(2.6, 1.75, 0.95, 6, 0.15)), body));
  const seam = new THREE.Mesh(track(new RoundedBoxGeometry(2.62, 0.045, 0.97, 2, 0.02)), metal);
  seam.position.y = 0.12;
  group.add(seam);
  const handle = new THREE.Mesh(track(new THREE.TorusGeometry(0.45, 0.06, 20, 56, Math.PI)), metal);
  handle.position.y = 0.87;
  group.add(handle);
  const claspGeometry = track(new RoundedBoxGeometry(0.24, 0.34, 0.1, 4, 0.04));
  [-0.72, 0.72].forEach((x) => {
    const clasp = new THREE.Mesh(claspGeometry, metal);
    clasp.position.set(x, 0.12, 0.5);
    group.add(clasp);
  });
  group.rotation.x = 0.22;
  const holder = new THREE.Group();
  holder.add(group);
  scene.add(holder);

  let smooth = 0;
  return {
    update: (t, _dt, pointer) => {
      smooth += (pointer - smooth) * 0.05;
      holder.rotation.y = smooth * 0.5 + Math.sin(t * 0.5) * 0.45;
      holder.position.y = Math.sin(t * 0.9) * 0.08;
    },
    dispose: () => disposables.forEach((d) => d.dispose()),
  };
};

/**
 * Real WebGL objects (PBR clearcoat materials, studio reflections, soft shadows), the way resend.com's hero cube is
 * rendered, instead of CSS imitations. Pauses off-screen; renders one still frame when motion is reduced.
 */
const Object3D = ({ variant, value = 76, className = "" }: { variant: Object3DVariant; value?: number; className?: string }) => {
  const host = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(false);

  // a WebGL context only lives while the object is on (or near) the screen
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const io = new IntersectionObserver(([entry]) => setActive(entry.isIntersecting), { rootMargin: "300px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    const el = host.current;
    if (!el || !active) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      return; // no WebGL: the surface keeps its flat background
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = variant === "ring" || variant === "database";
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);
    renderer.domElement.style.cssText = "display:block;width:100%;height:100%";

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    scene.environment = pmrem.fromScene(room, 0.04).texture;
    scene.environmentIntensity = 1.1;
    const camera = new THREE.PerspectiveCamera(variant === "gauge" ? 30 : 28, 1, 0.1, 50);

    const built =
      variant === "ring"
        ? buildRing(scene, camera)
        : variant === "hub"
          ? buildHub(scene, camera)
          : variant === "handset"
            ? buildHandset(scene, camera)
            : variant === "whatsapp"
              ? buildWhatsApp(scene, camera)
              : variant === "briefcase"
                ? buildBriefcase(scene, camera)
                : variant === "clipboard"
                  ? buildClipboard(scene, camera)
                  : variant === "database"
                    ? buildDatabase(scene, camera)
                    : buildGauge(scene, camera, value);

    let pointer = 0;
    const onMove = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      pointer = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width - 0.5) * 2));
    };
    window.addEventListener("pointermove", onMove, { passive: true });

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = el;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    resize();

    let raf = 0;
    let visible = true;
    let last = 0;
    const clock = new THREE.Clock();
    const frame = () => {
      raf = requestAnimationFrame(frame);
      if (!visible) {
        clock.getDelta();
        return;
      }
      const t = clock.getElapsedTime();
      built.update(t, t - last, pointer);
      last = t;
      renderer.render(scene, camera);
    };
    if (reduced) {
      built.update(variant === "gauge" ? 2 : 1.4, 0, 0);
      renderer.render(scene, camera);
    } else {
      frame();
    }

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    io.observe(el);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      observer.disconnect();
      window.removeEventListener("pointermove", onMove);
      built.dispose();
      pmrem.dispose();
      room.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [variant, value, active]);

  return <div ref={host} className={className} aria-hidden />;
};

export default Object3D;
