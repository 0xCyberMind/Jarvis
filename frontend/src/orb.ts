import * as THREE from "three";

export class OrbVisualizer {
  private scene = new THREE.Scene();
  private camera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
  private renderer = new THREE.WebGLRenderer({ antialias: true });
  private mesh: THREE.Mesh;
  private intensity = 1;

  constructor(container: HTMLElement) {
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(this.renderer.domElement);

    this.camera.position.z = 2.5;
    const geometry = new THREE.IcosahedronGeometry(1, 5);
    const material = new THREE.MeshStandardMaterial({ color: 0x22d3ee, wireframe: true });
    this.mesh = new THREE.Mesh(geometry, material);

    const light = new THREE.PointLight(0xffffff, 25);
    light.position.set(5, 5, 5);
    this.scene.add(this.mesh, light);

    window.addEventListener("resize", () => {
      const width = container.clientWidth;
      const height = container.clientHeight;
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.renderer.setSize(width, height);
    });

    this.animate();
  }

  setSpeaking(active: boolean): void {
    this.intensity = active ? 1.8 : 1;
  }

  private animate = (): void => {
    requestAnimationFrame(this.animate);
    this.mesh.rotation.x += 0.003 * this.intensity;
    this.mesh.rotation.y += 0.004 * this.intensity;
    this.mesh.scale.setScalar(1 + 0.03 * Math.sin(Date.now() * 0.005 * this.intensity));
    this.renderer.render(this.scene, this.camera);
  };
}
