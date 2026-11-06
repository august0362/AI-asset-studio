import { useI18n } from "../i18n";
import { useTheme } from "../theme/ThemeProvider";
import type { TranslationKey } from "../i18n/en";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { Maximize2, RotateCcw } from "lucide-react";

export default function GlbViewer({ url }: { url: string }) {
  const { t, label } = useI18n();
  const host = useRef<HTMLDivElement>(null),
    actions = useRef<(preset: string) => void>(),
    applyTheme = useRef<() => void>();
  const { theme } = useTheme();
  const [state, setState] = useState<TranslationKey>("copy.loadingGlb"),
    [error, setError] = useState(false),
    [wireframe, setWireframe] = useState(false);
  useEffect(() => {
    const mount = host.current!;
    let disposed = false;
    let object: THREE.Group | undefined;
    let renderer: THREE.WebGLRenderer;
    setState("copy.loadingGlb");
    setError(false);
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setState(
        "copy.webglIsUnavailableDownloadTheGlbToInspectItInACompatibleViewer",
      );
      setError(true);
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.append(renderer.domElement);
    renderer.domElement.tabIndex = 0;
    const scene = new THREE.Scene(),
      camera = new THREE.PerspectiveCamera(38, 1, 0.01, 1000);
    // Asset illumination keeps its original values in every theme (THEMES §4).
    scene.add(new THREE.HemisphereLight(13233663, 1581880, 3));
    const key = new THREE.DirectionalLight(16777215, 4);
    key.position.set(3, 5, 3);
    scene.add(key);
    const rim = new THREE.DirectionalLight(5036022, 2);
    rim.position.set(-4, 2, -3);
    scene.add(rim);
    const grid = new THREE.GridHelper(12, 24);
    grid.position.y = -0.77;
    scene.add(grid);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.screenSpacePanning = true;
    controls.minDistance = 0.5;
    controls.maxDistance = 25;
    const target = new THREE.Vector3();
    let distance = 4.6;
    const render = () => {
      if (!disposed) renderer.render(scene, camera);
    };
    const colors = () => {
      const style = getComputedStyle(document.documentElement);
      scene.background = new THREE.Color(
        style.getPropertyValue("--viewer-bg").trim(),
      );
      for (const material of Array.isArray(grid.material)
        ? grid.material
        : [grid.material]) {
        material.vertexColors = false;
        material.color.set(style.getPropertyValue("--viewer-grid").trim());
      }
      render();
    };
    applyTheme.current = colors;
    colors();
    const preset = (mode: string) => {
      if (mode === "wireframe") {
        object?.traverse((node) => {
          if (node instanceof THREE.Mesh)
            for (const material of Array.isArray(node.material)
              ? node.material
              : [node.material])
              if (material instanceof THREE.MeshStandardMaterial)
                material.wireframe = !material.wireframe;
        });
        render();
        return;
      }
      const direction =
        mode === "front"
          ? new THREE.Vector3(0, 0, 1)
          : mode === "side"
            ? new THREE.Vector3(1, 0, 0)
            : mode === "top"
              ? new THREE.Vector3(0, 1, 0.001)
              : new THREE.Vector3(1.4, 1.05, 1.6).normalize();
      controls.target.copy(target);
      camera.position.copy(target).addScaledVector(direction, distance);
      controls.update();
      render();
    };
    actions.current = preset;
    preset("perspective");
    controls.addEventListener("change", render);
    const resize = () => {
      const width = mount.clientWidth,
        height = mount.clientHeight;
      renderer.setSize(width, height);
      camera.aspect = width / Math.max(1, height);
      camera.updateProjectionMatrix();
      render();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    resize();
    const keyboard = (e: KeyboardEvent) => {
      if (e.key === "+" || e.key === "=" || e.key === "-") {
        e.preventDefault();
        const scale = e.key === "-" ? 1.15 : 0.87;
        camera.position
          .sub(controls.target)
          .multiplyScalar(scale)
          .add(controls.target);
        controls.update();
        render();
      }
      if (e.key.startsWith("Arrow")) {
        e.preventDefault();
        const delta =
          e.key === "ArrowLeft" || e.key === "ArrowDown" ? -0.12 : 0.12;
        if (e.shiftKey) {
          const shift = new THREE.Vector3(
            e.key === "ArrowLeft" || e.key === "ArrowRight" ? delta : 0,
            e.key === "ArrowUp" || e.key === "ArrowDown" ? delta : 0,
            0,
          ).applyQuaternion(camera.quaternion);
          camera.position.add(shift);
          controls.target.add(shift);
        } else {
          const offset = camera.position.clone().sub(controls.target),
            spherical = new THREE.Spherical().setFromVector3(offset);
          if (e.key === "ArrowLeft" || e.key === "ArrowRight")
            spherical.theta += delta;
          else
            spherical.phi = Math.max(
              0.1,
              Math.min(Math.PI - 0.1, spherical.phi + delta),
            );
          camera.position
            .copy(controls.target)
            .add(new THREE.Vector3().setFromSpherical(spherical));
        }
        controls.update();
        render();
      }
    };
    renderer.domElement.addEventListener("keydown", keyboard);
    new GLTFLoader().load(
      url,
      (gltf) => {
        if (disposed) {
          disposeObject(gltf.scene);
          return;
        }
        object = gltf.scene;
        scene.add(object);
        const box = new THREE.Box3().setFromObject(object);
        box.getCenter(target);
        const size = box.getSize(new THREE.Vector3()).length();
        distance = Math.max(size * 1.8, 1);
        grid.position.y = box.min.y - 0.01;
        setState("copy.glbLoadedTexturedFixture");
        setWireframe(false);
        preset("perspective");
      },
      undefined,
      () => {
        if (!disposed) {
          setError(true);
          setState("copy.couldNotLoadTheGlbDownloadTheFileOrTryAgain");
        }
      },
    );
    return () => {
      disposed = true;
      observer.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("keydown", keyboard);
      disposeObject(scene);
      renderer.dispose();
      renderer.domElement.remove();
      actions.current = undefined;
      applyTheme.current = undefined;
    };
  }, [url]);
  useEffect(() => {
    applyTheme.current?.();
  }, [theme]);
  useEffect(() => {
    host.current
      ?.querySelector("canvas")
      ?.setAttribute(
        "aria-label",
        t(
          "copy.interactive3DPreviewArrowKeysOrbitShiftPlusArrowsPansPlusAndMinusZoom",
        ),
      );
  }, [t, url]);
  return (
    <div className="glb-viewer">
      <div className="viewer-toolbar">
        <span>
          <Maximize2 size={14} aria-hidden="true" />
          {t("copy.3dViewport")}
        </span>
        <button
          aria-pressed={wireframe}
          disabled={error || state === "copy.loadingGlb"}
          onClick={() => {
            actions.current?.("wireframe");
            setWireframe((v) => !v);
          }}
        >
          {t("copy.wireframe")}
        </button>
      </div>
      <div className="canvas-host" ref={host} />
      <div
        className={`viewer-status ${error ? "danger-text" : ""}`}
        role="status"
      >
        {t(state)}
      </div>
      <div className="camera-toolbar" aria-label={t("copy.cameraControls")}>
        {["perspective", "front", "side", "top"].map((p) => (
          <button key={p} onClick={() => actions.current?.(p)} disabled={error}>
            {label("camera", p)}
          </button>
        ))}
        <button
          onClick={() => actions.current?.("perspective")}
          disabled={error}
        >
          <RotateCcw size={13} aria-hidden="true" />
          {t("copy.resetView")}
        </button>
      </div>
      <p className="viewer-help">
        {t(
          "copy.dragToOrbitScrollToZoomRightDragToPanFocusTheCanvasForKeyboardControls",
        )}
      </p>
    </div>
  );
}
function disposeObject(root: THREE.Object3D) {
  root.traverse((node) => {
    if (node instanceof THREE.Mesh) {
      node.geometry.dispose();
      for (const material of Array.isArray(node.material)
        ? node.material
        : [node.material]) {
        for (const value of Object.values(material))
          if (value instanceof THREE.Texture) {
            value.dispose();
            if (value.image instanceof ImageBitmap) value.image.close();
          }
        material.dispose();
      }
    } else if (node instanceof THREE.LineSegments) {
      node.geometry.dispose();
      for (const material of Array.isArray(node.material)
        ? node.material
        : [node.material])
        material.dispose();
    }
  });
}
