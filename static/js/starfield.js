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

    const stars = [];
    const numStars = 150;

    for (let i = 0; i < numStars; i++) {
        stars.push({
            x: Math.random() * width,
            y: Math.random() * height,
            radius: Math.random() * 1.5 + 0.5,
            alpha: Math.random(),
            speed: Math.random() * 0.02 + 0.005,
            color: Math.random() > 0.3 ? '#38bdf8' : (Math.random() > 0.5 ? '#ffffff' : '#a855f7')
        });
    }

    function render() {
        ctx.clearRect(0, 0, width, height);

        stars.forEach(star => {
            star.alpha += star.speed;
            if (star.alpha > 1 || star.alpha < 0.2) {
                star.speed = -star.speed;
            }

            ctx.beginPath();
            ctx.arc(star.x, star.y, star.radius, 0, Math.PI * 2);
            ctx.fillStyle = star.color;
            ctx.globalAlpha = Math.abs(star.alpha);
            ctx.fill();

            star.y -= 0.15;
            if (star.y < 0) {
                star.y = height;
                star.x = Math.random() * width;
            }
        });

        requestAnimationFrame(render);
    }

    render();
});
