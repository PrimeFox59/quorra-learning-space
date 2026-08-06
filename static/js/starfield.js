// Interactive Starfield Background Animation
document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.createElement('canvas');
    canvas.id = 'starfield-canvas';
    document.body.prepend(canvas);

    const ctx = canvas.getContext('2d');

    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    window.addEventListener('resize', () => {
        width = canvas.width = window.innerWidth;
        height = canvas.height = window.innerHeight;
    });

    let isWarping = true;
    let warpSpeedMultiplier = 25; // Kecepatan tinggi saat pertama dibuka (Lorong Dimensi)
    
    // Kurangi kecepatan secara mulus (smooth deceleration) menjadi normal starfield
    setTimeout(() => {
        const decelerationTimer = setInterval(() => {
            warpSpeedMultiplier *= 0.88;
            if (warpSpeedMultiplier <= 1.05) {
                warpSpeedMultiplier = 1;
                isWarping = false;
                clearInterval(decelerationTimer);
            }
        }, 50);
    }, 400);

    const stars = [];
    const numStars = 220;

    for (let i = 0; i < numStars; i++) {
        stars.push({
            x: (Math.random() - 0.5) * width,
            y: (Math.random() - 0.5) * height,
            z: Math.random() * width,
            radius: Math.random() * 1.5 + 0.5,
            alpha: Math.random(),
            speed: Math.random() * 0.02 + 0.005,
            color: Math.random() > 0.3 ? '#00f0ff' : (Math.random() > 0.5 ? '#ffffff' : '#a855f7')
        });
    }

    function render() {
        ctx.clearRect(0, 0, width, height);

        const centerX = width / 2;
        const centerY = height / 2;

        stars.forEach(star => {
            // Gerakan bintang keluar dari pusat (Perspective Warp Tunnel)
            star.z -= 4 * warpSpeedMultiplier;
            if (star.z <= 0) {
                star.z = width;
                star.x = (Math.random() - 0.5) * width;
                star.y = (Math.random() - 0.5) * height;
            }

            const k = 250 / star.z;
            const px = star.x * k + centerX;
            const py = star.y * k + centerY;

            if (px >= 0 && px <= width && py >= 0 && py <= height) {
                const size = (1 - star.z / width) * 3;
                
                ctx.beginPath();
                if (isWarping) {
                    // Gambar garis streaking / distorsi lorong dimensi
                    const prevK = 250 / (star.z + 15 * warpSpeedMultiplier);
                    const prevPx = star.x * prevK + centerX;
                    const prevPy = star.y * prevK + centerY;

                    ctx.strokeStyle = star.color;
                    ctx.lineWidth = size * 0.8;
                    ctx.globalAlpha = Math.min(1, (1 - star.z / width) * 1.5);
                    ctx.moveTo(px, py);
                    ctx.lineTo(prevPx, prevPy);
                    ctx.stroke();
                } else {
                    ctx.arc(px, py, Math.max(0.5, size), 0, Math.PI * 2);
                    ctx.fillStyle = star.color;
                    ctx.globalAlpha = Math.abs(star.alpha);
                    ctx.fill();
                }
            }
        });

        requestAnimationFrame(render);
    }

    render();

    // Spawn Warp Tunnel Overlay Element dynamically
    const overlay = document.createElement('div');
    overlay.id = 'warp-tunnel-overlay';
    overlay.innerHTML = `
        <div class="warp-ring" style="animation-delay: 0s;"></div>
        <div class="warp-ring" style="animation-delay: 0.3s;"></div>
        <div class="warp-ring" style="animation-delay: 0.6s;"></div>
        <div class="warp-ring" style="animation-delay: 0.9s;"></div>
        <div class="relative z-10 text-center space-y-2 font-mono">
            <div class="w-12 h-12 rounded-2xl bg-cyan-950 border border-cyan-400 text-cyan-300 mx-auto flex items-center justify-center text-2xl shadow-lg shadow-cyan-500/50 animate-bounce">
                <i class="bi bi-rocket-takeoff-fill"></i>
            </div>
            <span class="block text-xs font-black text-cyan-300 uppercase tracking-widest animate-pulse">MEMASUKI LORONG DIMENSI QUORRA SPACE...</span>
        </div>
    `;
    document.body.prepend(overlay);
    document.body.classList.add('warp-distortion-active');

    setTimeout(() => {
        overlay.classList.add('fade-out');
        setTimeout(() => {
            overlay.remove();
            document.body.classList.remove('warp-distortion-active');
        }, 800);
    }, 1100);
});
