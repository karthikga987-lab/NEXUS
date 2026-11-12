
import { useEffect, useRef } from 'react';
import './CosmicBackground.css';

export default function CosmicBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');

    if (!ctx) return;

    const reduceMotion = window.matchMedia(
      '(prefers-reduced-motion: reduce)'
    ).matches;

    let width = 0;
    let height = 0;
    let animationId;
    let time = 0;

    const pointer = {
      x: -1000,
      y: -1000,
      targetX: -1000,
      targetY: -1000,
      active: false,
    };

    const stars = [];
    const starCount = 100;

    function resizeCanvas() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);

      width = window.innerWidth;
      height = window.innerHeight;

      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      stars.length = 0;

      for (let i = 0; i < starCount; i++) {
        stars.push({
          x: Math.random() * width,
          y: Math.random() * height,
          radius: Math.random() * 1.5 + 0.3,
          alpha: Math.random() * 0.65 + 0.2,
          speed: Math.random() * 0.008 + 0.002,
          phase: Math.random() * Math.PI * 2,
        });
      }
    }

    function drawNebula() {
      const glow = ctx.createRadialGradient(
        width * 0.5,
        height * 0.42,
        0,
        width * 0.5,
        height * 0.42,
        Math.max(width, height) * 0.72
      );

      glow.addColorStop(0, 'rgba(103, 65, 173, 0.13)');
      glow.addColorStop(0.38, 'rgba(75, 48, 132, 0.07)');
      glow.addColorStop(1, 'rgba(5, 4, 12, 0)');

      ctx.fillStyle = glow;
      ctx.fillRect(0, 0, width, height);

      const purpleGlow = ctx.createRadialGradient(
        width * 0.78,
        height * 0.72,
        0,
        width * 0.78,
        height * 0.72,
        Math.min(width, height) * 0.55
      );

      purpleGlow.addColorStop(0, 'rgba(142, 91, 210, 0.09)');
      purpleGlow.addColorStop(1, 'rgba(142, 91, 210, 0)');

      ctx.fillStyle = purpleGlow;
      ctx.fillRect(0, 0, width, height);
    }

    function drawStars() {
      stars.forEach((star) => {
        const twinkle = reduceMotion
          ? 1
          : 0.65 + Math.sin(time * star.speed + star.phase) * 0.35;

        ctx.beginPath();
        ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);

        ctx.fillStyle = `rgba(225, 213, 255, ${star.alpha * twinkle})`;
        ctx.fill();
      });
    }

    function drawWaves() {
      const waveCount = 11;
      const spacing = height / 13;

      for (let wave = 0; wave < waveCount; wave++) {
        ctx.beginPath();

        const baseY = spacing * (wave + 1);
        const amplitude = 18 + wave * 1.5;

        for (let x = 0; x <= width + 10; x += 8) {
          const normalizedX = x / width;

          let y =
            baseY +
            Math.sin(normalizedX * 5 + time * 0.004 + wave * 0.45) *
              amplitude +
            Math.sin(normalizedX * 9 - time * 0.002 + wave) * 8;

          if (pointer.active) {
            const dx = x - pointer.x;
            const dy = y - pointer.y;
            const distance = Math.sqrt(dx * dx + dy * dy);
            const radius = 190;

            if (distance < radius) {
              const force = (1 - distance / radius) ** 2;
              const direction = dy === 0 ? 1 : dy / (distance || 1);

              y += direction * force * 55;
            }
          }

          if (x === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }

        const opacity = 0.055 + (wave % 3) * 0.015;

        ctx.strokeStyle =
          wave % 3 === 0
            ? `rgba(190, 157, 255, ${opacity})`
            : `rgba(215, 211, 235, ${opacity})`;

        ctx.lineWidth = wave % 3 === 0 ? 1.2 : 0.8;
        ctx.stroke();
      }
    }

    function draw() {
      pointer.x += (pointer.targetX - pointer.x) * 0.12;
      pointer.y += (pointer.targetY - pointer.y) * 0.12;

      ctx.clearRect(0, 0, width, height);

      drawNebula();
      drawWaves();
      drawStars();

      if (!reduceMotion) {
        time += 1;
        animationId = requestAnimationFrame(draw);
      }
    }

    function handlePointerMove(event) {
      pointer.targetX = event.clientX;
      pointer.targetY = event.clientY;
      pointer.active = true;
    }

    function handlePointerLeave() {
      pointer.active = false;
      pointer.targetX = -1000;
      pointer.targetY = -1000;
    }

    resizeCanvas();
    draw();

    if (!reduceMotion) {
      animationId = requestAnimationFrame(draw);
    }

    window.addEventListener('resize', resizeCanvas);
    window.addEventListener('pointermove', handlePointerMove);
    document.addEventListener('pointerleave', handlePointerLeave);

    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener('resize', resizeCanvas);
      window.removeEventListener('pointermove', handlePointerMove);
      document.removeEventListener('pointerleave', handlePointerLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="cosmic-background"
      aria-hidden="true"
    />
  );
}
