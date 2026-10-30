import React, { useEffect, useRef } from 'react';

/**
 * SpatialCanvas - High-Performance Interactive 3D Particle & Geometric Wireframe Mesh
 * Renders an ethereal, ambient 3D depth-field that gently tracks mouse movement
 * and renders floating geometric cryptographic nodes.
 */
export default function SpatialCanvas() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    let mouseX = width / 2;
    let mouseY = height / 2;
    let targetMouseX = mouseX;
    let targetMouseY = mouseY;

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    const handleMouseMove = (e: MouseEvent) => {
      targetMouseX = e.clientX;
      targetMouseY = e.clientY;
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('mousemove', handleMouseMove);

    // 3D Particles
    const PARTICLE_COUNT = 55;
    interface Particle3D {
      x: number;
      y: number;
      z: number;
      radius: number;
      color: string;
      speedZ: number;
      pulse: number;
    }

    const colors = [
      'rgba(99, 102, 241, 0.45)', // indigo
      'rgba(14, 165, 233, 0.40)', // cyan
      'rgba(168, 85, 247, 0.40)', // purple
      'rgba(16, 185, 129, 0.35)', // emerald
    ];

    const particles: Particle3D[] = [];
    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push({
        x: (Math.random() - 0.5) * width * 1.5,
        y: (Math.random() - 0.5) * height * 1.5,
        z: Math.random() * 800 + 100,
        radius: Math.random() * 2.2 + 0.8,
        color: colors[i % colors.length],
        speedZ: Math.random() * 0.4 + 0.15,
        pulse: Math.random() * Math.PI * 2,
      });
    }

    // 3D Rotating Icosahedron Vertices
    const phi = (1 + Math.sqrt(5)) / 2;
    const icoVertices: [number, number, number][] = [
      [-1, phi, 0], [1, phi, 0], [-1, -phi, 0], [1, -phi, 0],
      [0, -1, phi], [0, 1, phi], [0, -1, -phi], [0, 1, -phi],
      [phi, 0, -1], [phi, 0, 1], [-phi, 0, -1], [-phi, 0, 1]
    ].map(([x, y, z]) => {
      const len = Math.sqrt(x*x + y*y + z*z);
      return [(x / len) * 75, (y / len) * 75, (z / len) * 75];
    });

    // Edges connecting vertices with distance threshold
    const icoEdges: [number, number][] = [];
    for (let i = 0; i < icoVertices.length; i++) {
      for (let j = i + 1; j < icoVertices.length; j++) {
        const dx = icoVertices[i][0] - icoVertices[j][0];
        const dy = icoVertices[i][1] - icoVertices[j][1];
        const dz = icoVertices[i][2] - icoVertices[j][2];
        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
        if (dist < 85) {
          icoEdges.push([i, j]);
        }
      }
    }

    let rotX = 0;
    let rotY = 0;
    let rotZ = 0;

    const render = () => {
      // Smooth camera interpolation
      mouseX += (targetMouseX - mouseX) * 0.04;
      mouseY += (targetMouseY - mouseY) * 0.04;

      const camOffsetX = (mouseX - width / 2) * 0.08;
      const camOffsetY = (mouseY - height / 2) * 0.08;

      ctx.clearRect(0, 0, width, height);

      // Render 3D Perspective Particles
      const fov = 450;
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.z -= p.speedZ;
        p.pulse += 0.02;

        if (p.z <= 20) {
          p.z = 900;
          p.x = (Math.random() - 0.5) * width * 1.5;
          p.y = (Math.random() - 0.5) * height * 1.5;
        }

        const scale = fov / (fov + p.z);
        const projX = (p.x - camOffsetX) * scale + width / 2;
        const projY = (p.y - camOffsetY) * scale + height / 2;

        if (projX >= 0 && projX <= width && projY >= 0 && projY <= height) {
          const alpha = Math.min(1, Math.max(0.1, (1 - p.z / 900) * 0.7));
          const size = p.radius * scale * (1 + Math.sin(p.pulse) * 0.2);

          ctx.beginPath();
          ctx.arc(projX, projY, size, 0, Math.PI * 2);
          ctx.fillStyle = p.color.replace(/[\d\.]+\)$/, `${alpha})`);
          ctx.fill();

          // Subtle glow
          if (scale > 0.6) {
            ctx.beginPath();
            ctx.arc(projX, projY, size * 2.5, 0, Math.PI * 2);
            ctx.fillStyle = p.color.replace(/[\d\.]+\)$/, `${alpha * 0.2})`);
            ctx.fill();
          }
        }
      }

      // Render Subtle Floating 3D Geometric Nodes in the corner background
      rotX += 0.003;
      rotY += 0.004;
      rotZ += 0.002;

      const renderPolyhedron = (centerX: number, centerY: number, scaleMultiplier: number, strokeColor: string) => {
        const cosX = Math.cos(rotX), sinX = Math.sin(rotX);
        const cosY = Math.cos(rotY), sinY = Math.sin(rotY);
        const cosZ = Math.cos(rotZ), sinZ = Math.sin(rotZ);

        const projected: [number, number, number][] = icoVertices.map(([vx, vy, vz]) => {
          // 3D rotation
          let x1 = vx * cosY + vz * sinY;
          let y1 = vy;
          let z1 = -vx * sinY + vz * cosY;

          let x2 = x1;
          let y2 = y1 * cosX - z1 * sinX;
          let z2 = y1 * sinX + z1 * cosX;

          let x3 = x2 * cosZ - y2 * sinZ;
          let y3 = x2 * sinZ + y2 * cosZ;
          let z3 = z2;

          const depth = 350 + z3;
          const s = (300 / depth) * scaleMultiplier;
          return [centerX + x3 * s, centerY + y3 * s, z3];
        });

        ctx.strokeStyle = strokeColor;
        ctx.lineWidth = 1.2;

        icoEdges.forEach(([i, j]) => {
          const [x1, y1] = projected[i];
          const [x2, y2] = projected[j];
          ctx.beginPath();
          ctx.moveTo(x1, y1);
          ctx.lineTo(x2, y2);
          ctx.stroke();
        });

        // Vertices points
        projected.forEach(([x, y]) => {
          ctx.beginPath();
          ctx.arc(x, y, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = strokeColor.replace('0.15', '0.45').replace('0.25', '0.65');
          ctx.fill();
        });
      };

      // Top right background decorative geometric node
      renderPolyhedron(width * 0.88, height * 0.18, 0.85, 'rgba(99, 102, 241, 0.18)');
      // Bottom left background decorative geometric node
      renderPolyhedron(width * 0.12, height * 0.82, 0.70, 'rgba(14, 165, 233, 0.14)');

      animId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="spatial-canvas"
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        width: '100vw',
        height: '100vh',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  );
}

