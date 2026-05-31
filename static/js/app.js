document.addEventListener('DOMContentLoaded', () => {
    // ----------------------------------------------------
    // 1. GLOBAL 3D PARTICLE BACKGROUND
    // ----------------------------------------------------
    const bgCanvas = document.getElementById('bg-canvas');
    if (bgCanvas) {
        initBackgroundParticles(bgCanvas);
    }

    // ----------------------------------------------------
    // 2. INTERACTIVE 3D DNA HELIX (HOMEPAGE)
    // ----------------------------------------------------
    const dnaContainer = document.getElementById('dna-container-3d');
    if (dnaContainer) {
        initDNAHelix(dnaContainer);
    }

    // ----------------------------------------------------
    // 3. HOLOGRAPHIC 3D SCANNING TRANSITION
    // ----------------------------------------------------
    // 3. HOLOGRAPHIC 3D SCANNING TRANSITION
    // ----------------------------------------------------
    const diagnosisForm = document.getElementById('diagnosis-form');
    if (diagnosisForm) {
        setupDiagnosisScanner(diagnosisForm);
    }

    // ----------------------------------------------------
    // 4. MICRO-INTERACTIONS (BUTTON HOVERS)
    // ----------------------------------------------------
    const buttons = document.querySelectorAll('.button');
    buttons.forEach(button => {
        button.addEventListener('mouseenter', () => {
            gsap.to(button, { scale: 1.05, duration: 0.3, ease: 'power2.out' });
        });
        button.addEventListener('mouseleave', () => {
            gsap.to(button, { scale: 1.0, duration: 0.3, ease: 'power2.out' });
        });
    });

    // ----------------------------------------------------
    // 5. PREMIUM TELEHEALTH CONSULTATION CHAT INITIALIZATION
    // ----------------------------------------------------
    const chatForm = document.getElementById('consultation-chat-form');
    if (chatForm) {
        initTelehealthChat(chatForm);
    }
});

// ========================================================
// BACKGROUND PARTICLE CONSTELATION IMPLEMENTATION
// ========================================================
function initBackgroundParticles(canvas) {
    const renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 100);
    camera.position.z = 30;

    // Adjust canvas size
    function resize() {
        camera.aspect = window.innerWidth / window.innerHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(window.innerWidth, window.innerHeight);
    }
    window.addEventListener('resize', resize);
    resize();

    // Create particles
    const particleCount = 70;
    const geometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const velocities = [];
    const minDistance = 9;

    for (let i = 0; i < particleCount; i++) {
        // Random positions in a box
        positions[i * 3] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 1] = (Math.random() - 0.5) * 40;
        positions[i * 3 + 2] = (Math.random() - 0.5) * 40;

        velocities.push({
            x: (Math.random() - 0.5) * 0.03,
            y: (Math.random() - 0.5) * 0.03,
            z: (Math.random() - 0.5) * 0.03
        });
    }

    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

    // Particle material
    const material = new THREE.PointsMaterial({
        color: 0x14b8a6,
        size: 0.25,
        transparent: true,
        opacity: 0.7
    });

    const particles = new THREE.Points(geometry, material);
    scene.add(particles);

    // Line segments connecting close particles
    const lineMat = new THREE.LineBasicMaterial({
        color: 0x0d9488,
        transparent: true,
        opacity: 0.15
    });

    let lineSegments;

    // Track mouse for interactive camera parallax
    let mouseX = 0;
    let mouseY = 0;
    let targetX = 0;
    let targetY = 0;

    window.addEventListener('mousemove', (e) => {
        mouseX = (e.clientX - window.innerWidth / 2) * 0.05;
        mouseY = (e.clientY - window.innerHeight / 2) * 0.05;
    });

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        // Slow float particles
        const posAttr = geometry.attributes.position;
        const array = posAttr.array;

        for (let i = 0; i < particleCount; i++) {
            array[i * 3] += velocities[i].x;
            array[i * 3 + 1] += velocities[i].y;
            array[i * 3 + 2] += velocities[i].z;

            // Boundary bounce
            if (Math.abs(array[i * 3]) > 25) velocities[i].x *= -1;
            if (Math.abs(array[i * 3 + 1]) > 25) velocities[i].y *= -1;
            if (Math.abs(array[i * 3 + 2]) > 25) velocities[i].z *= -1;
        }
        posAttr.needsUpdate = true;

        // Clean old line segment mesh
        if (lineSegments) {
            scene.remove(lineSegments);
            lineSegments.geometry.dispose();
        }

        // Calculate close connections
        const linePoints = [];
        for (let i = 0; i < particleCount; i++) {
            const xi = array[i * 3];
            const yi = array[i * 3 + 1];
            const zi = array[i * 3 + 2];

            for (let j = i + 1; j < particleCount; j++) {
                const xj = array[j * 3];
                const yj = array[j * 3 + 1];
                const zj = array[j * 3 + 2];

                const dx = xi - xj;
                const dy = yi - yj;
                const dz = zi - zj;
                const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);

                if (dist < minDistance) {
                    linePoints.push(new THREE.Vector3(xi, yi, zi));
                    linePoints.push(new THREE.Vector3(xj, yj, zj));
                }
            }
        }

        if (linePoints.length > 0) {
            const lineGeom = new THREE.BufferGeometry().setFromPoints(linePoints);
            lineSegments = new THREE.LineSegments(lineGeom, lineMat);
            scene.add(lineSegments);
        }

        // Camera Parallax Easing
        targetX += (mouseX - targetX) * 0.05;
        targetY += (mouseY - targetY) * 0.05;

        camera.position.x = targetX;
        camera.position.y = -targetY;
        camera.lookAt(scene.position);

        renderer.render(scene, camera);
    }

    animate();
}

// ========================================================
// 3D DNA HELIX IMPLEMENTATION
// ========================================================
function initDNAHelix(container) {
    // Clear loading placeholder
    container.innerHTML = '';

    const width = container.clientWidth;
    const height = container.clientHeight;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
    camera.position.z = 24;

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0x06b6d4, 1.2); // Cyan Light
    dirLight1.position.set(10, 10, 10);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0x10b981, 1.2); // Emerald Light
    dirLight2.position.set(-10, -10, -10);
    scene.add(dirLight2);

    // Build DNA group
    const dnaGroup = new THREE.Group();
    const rungsCount = 30;
    const helixRadius = 3.5;
    const helixHeight = 12.0;

    const sphereGeom = new THREE.SphereGeometry(0.38, 16, 16);
    const strand1Material = new THREE.MeshPhongMaterial({ color: 0x10b981, emissive: 0x059669, shininess: 80 });
    const strand2Material = new THREE.MeshPhongMaterial({ color: 0x06b6d4, emissive: 0x0891b2, shininess: 80 });
    const rungMaterial = new THREE.MeshPhongMaterial({ color: 0x94a3b8, transparent: true, opacity: 0.7 });

    const nodes1 = [];
    const nodes2 = [];
    const rungs = [];

    for (let i = 0; i < rungsCount; i++) {
        // Parametric equations for double helix
        const t = (i / rungsCount) * Math.PI * 4; // Two complete rotations
        const y = (i / rungsCount) * helixHeight - (helixHeight / 2);

        // Strand 1 node
        const x1 = Math.sin(t) * helixRadius;
        const z1 = Math.cos(t) * helixRadius;
        const sphere1 = new THREE.Mesh(sphereGeom, strand1Material);
        sphere1.position.set(x1, y, z1);
        dnaGroup.add(sphere1);
        nodes1.push(sphere1);

        // Strand 2 node (shifted 180 degrees)
        const x2 = Math.sin(t + Math.PI) * helixRadius;
        const z2 = Math.cos(t + Math.PI) * helixRadius;
        const sphere2 = new THREE.Mesh(sphereGeom, strand2Material);
        sphere2.position.set(x2, y, z2);
        dnaGroup.add(sphere2);
        nodes2.push(sphere2);

        // Connecting Rung Cylinder
        const cylinderGeom = new THREE.CylinderGeometry(0.08, 0.08, 1, 8);
        const rung = new THREE.Mesh(cylinderGeom, rungMaterial);
        dnaGroup.add(rung);
        rungs.push({
            mesh: rung,
            idx: i,
            t: t,
            y: y
        });
    }

    scene.add(dnaGroup);

    // Position helper for rungs
    function updateRungPosition(rungInfo) {
        const t = rungInfo.t + dnaGroup.rotation.y;
        const y = rungInfo.y;

        const x1 = Math.sin(t) * helixRadius;
        const z1 = Math.cos(t) * helixRadius;
        
        const x2 = Math.sin(t + Math.PI) * helixRadius;
        const z2 = Math.cos(t + Math.PI) * helixRadius;

        // Place and scale cylinder to span between x1/z1 and x2/z2
        const p1 = new THREE.Vector3(x1, y, z1);
        const p2 = new THREE.Vector3(x2, y, z2);

        rungInfo.mesh.position.copy(p1).add(p2).multiplyScalar(0.5);
        rungInfo.mesh.scale.set(1, p1.distanceTo(p2), 1);

        // Rotate cylinder to point from p1 to p2
        const direction = new THREE.Vector3().subVectors(p2, p1).normalize();
        const alignAxis = new THREE.Vector3(0, 1, 0); // Cylinders default vertical
        const quaternion = new THREE.Quaternion().setFromUnitVectors(alignAxis, direction);
        rungInfo.mesh.quaternion.copy(quaternion);
    }

    // Drag-to-Rotate Interaction
    let isDragging = false;
    let previousMousePosition = { x: 0, y: 0 };
    let dragVelocity = { x: 0, y: 0 };

    container.addEventListener('mousedown', (e) => {
        isDragging = true;
        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const deltaMove = {
            x: e.clientX - previousMousePosition.x,
            y: e.clientY - previousMousePosition.y
        };

        dnaGroup.rotation.y += deltaMove.x * 0.005;
        dnaGroup.rotation.x += deltaMove.y * 0.005;

        dragVelocity = { x: deltaMove.x, y: deltaMove.y };
        previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
        isDragging = false;
    });

    // Resize Handler
    window.addEventListener('resize', () => {
        const w = container.clientWidth;
        const h = container.clientHeight;
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
    });

    // Hover acceleration
    let hoverSpeed = 0.008;
    container.addEventListener('mouseenter', () => {
        gsap.to({ val: hoverSpeed }, { val: 0.03, duration: 0.8, onUpdate: function() { hoverSpeed = this.targets()[0].val; } });
    });
    container.addEventListener('mouseleave', () => {
        gsap.to({ val: hoverSpeed }, { val: 0.008, duration: 1.2, onUpdate: function() { hoverSpeed = this.targets()[0].val; } });
    });

    // Wave animation offsets
    let tick = 0;

    // Animation Loop
    function animate() {
        requestAnimationFrame(animate);

        tick += 0.02;

        if (!isDragging) {
            // Apply inertial drag velocity decay
            dnaGroup.rotation.y += dragVelocity.x * 0.01 + hoverSpeed;
            dnaGroup.rotation.x += dragVelocity.y * 0.01;
            dragVelocity.x *= 0.95;
            dragVelocity.y *= 0.95;

            // Return x rotation to zero gently
            dnaGroup.rotation.x += (0 - dnaGroup.rotation.x) * 0.05;
        }

        // Apply a beautiful wave ripple through nodes
        for (let i = 0; i < rungsCount; i++) {
            const waveOffset = Math.sin(tick + i * 0.25) * 0.4;
            const t = (i / rungsCount) * Math.PI * 4;

            // Adjust helix radius dynamically to simulate breathing DNA
            const rad = helixRadius + waveOffset;

            // Update Strand 1
            nodes1[i].position.x = Math.sin(t) * rad;
            nodes1[i].position.z = Math.cos(t) * rad;

            // Update Strand 2
            nodes2[i].position.x = Math.sin(t + Math.PI) * rad;
            nodes2[i].position.z = Math.cos(t + Math.PI) * rad;
        }

        // Update connecting rungs
        rungs.forEach(rung => {
            const waveOffset = Math.sin(tick + rung.idx * 0.25) * 0.4;
            const t = rung.t;
            const y = rung.y;
            const rad = helixRadius + waveOffset;

            const p1 = new THREE.Vector3(Math.sin(t) * rad, y, Math.cos(t) * rad);
            const p2 = new THREE.Vector3(Math.sin(t + Math.PI) * rad, y, Math.cos(t + Math.PI) * rad);

            rung.mesh.position.copy(p1).add(p2).multiplyScalar(0.5);
            rung.mesh.scale.set(1, p1.distanceTo(p2), 1);

            const direction = new THREE.Vector3().subVectors(p2, p1).normalize();
            const alignAxis = new THREE.Vector3(0, 1, 0);
            const quaternion = new THREE.Quaternion().setFromUnitVectors(alignAxis, direction);
            rung.mesh.quaternion.copy(quaternion);
        });

        renderer.render(scene, camera);
    }

    animate();
}

// ========================================================
// 3D HOLOGRAPHIC DIAGNOSIS SCANNER
// ========================================================
function setupDiagnosisScanner(form) {
    const overlay = document.getElementById('scan-overlay');
    const viewport = document.getElementById('scan-viewport');
    const progressBar = document.getElementById('scan-progress-bar');
    const statusText = document.querySelector('.scan-status-text');
    const logs = document.getElementById('scan-logs');

    form.addEventListener('submit', (e) => {
        e.preventDefault();

        // Show Scan Overlay
        overlay.classList.remove('hidden');
        document.body.style.overflow = 'hidden'; // Lock scrolling

        // Init 3D Scan WebGL scene
        const width = viewport.clientWidth;
        const height = viewport.clientHeight;
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 100);
        camera.position.z = 18;

        const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(width, height);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        viewport.appendChild(renderer.domElement);

        // Add scan grid sphere
        const sphereGeom = new THREE.SphereGeometry(4, 24, 24);
        const wireframeMat = new THREE.MeshBasicMaterial({
            color: 0x14b8a6,
            wireframe: true,
            transparent: true,
            opacity: 0.3
        });
        const scannerSphere = new THREE.Mesh(sphereGeom, wireframeMat);
        scene.add(scannerSphere);

        // Holographic scanning rings
        const ringGeom1 = new THREE.TorusGeometry(4.2, 0.05, 8, 48);
        const ringMat1 = new THREE.MeshBasicMaterial({ color: 0x10b981, transparent: true, opacity: 0.8 });
        const scanRing1 = new THREE.Mesh(ringGeom1, ringMat1);
        scanRing1.rotation.x = Math.PI / 2;
        scene.add(scanRing1);

        const ringGeom2 = new THREE.TorusGeometry(4.2, 0.02, 8, 48);
        const ringMat2 = new THREE.MeshBasicMaterial({ color: 0x06b6d4, transparent: true, opacity: 0.6 });
        const scanRing2 = new THREE.Mesh(ringGeom2, ringMat2);
        scanRing2.rotation.x = Math.PI / 2;
        scene.add(scanRing2);

        // Dynamic laser grid helper
        const gridHelper = new THREE.GridHelper(12, 12, 0x0f766e, 0x0d9488);
        gridHelper.position.y = -4;
        scene.add(gridHelper);

        // Animation Loop for scanner viewport
        let time = 0;
        function animateScan() {
            requestAnimationFrame(animateScan);
            time += 0.02;

            // Spin sphere
            scannerSphere.rotation.y += 0.01;
            scannerSphere.rotation.x = Math.sin(time * 0.5) * 0.2;

            // Move scan rings up and down to simulate a scan laser beam
            scanRing1.position.y = Math.sin(time * 2) * 4;
            scanRing2.position.y = Math.sin(time * 2 + 0.3) * 4;
            
            // Pulse rings slightly
            const ringPulse = 1.0 + Math.sin(time * 4) * 0.05;
            scanRing1.scale.set(ringPulse, ringPulse, 1);

            renderer.render(scene, camera);
        }
        animateScan();

        // ----------------------------------------------------
        // SCANNING SEQUENCE TIMELINE (GSAP + LOGS)
        // ----------------------------------------------------
        const timeline = [
            { t: 0, pct: 10, status: "Establishing secure SSL connection to MediScan AI node...", log: "[CONNECT] Connected to node SECURE_M8." },
            { t: 0.8, pct: 28, status: "Retrieving patient bio-data logs and health records...", log: "[DB] Metadata extracted. Patient profile fetched." },
            { t: 1.6, pct: 52, status: "Parsing chief complaint text via clinical NLP models...", log: "[NLP] Tokenized symptoms, duration, and severity markers." },
            { t: 2.4, pct: 75, status: "Querying diagnostic databases & synthesizing report...", log: "[AI-CORE] Querying OpenRouter neural model (gpt-4o-mini)..." },
            { t: 3.2, pct: 92, status: "Structuring medical prescription Rx formatting...", log: "[Rx-CORE] Validating pharmaceutical dosing charts..." },
            { t: 3.8, pct: 100, status: "Prescription verification complete! Saving...", log: "[SUCCESS] Prescription compiled successfully." }
        ];

        timeline.forEach(step => {
            setTimeout(() => {
                // Update Progress bar
                gsap.to(progressBar, { width: `${step.pct}%`, duration: 0.4 });
                
                // Update Status text
                statusText.innerText = step.status;
                
                // Add Log Entry
                const entry = document.createElement('div');
                entry.className = "log-entry";
                entry.innerText = step.log;
                logs.appendChild(entry);
                logs.scrollTop = logs.scrollHeight; // Auto scroll
                
                // Flashing effect on logs
                gsap.fromTo(entry, { opacity: 0.2, x: -10 }, { opacity: 1, x: 0, duration: 0.2 });

            }, step.t * 1000);
        });

        // Submit form after animation completes
        setTimeout(() => {
            form.submit();
        }, 4400);
    });
}

// ========================================================
// PREMIUM TELEHEALTH CONSULTATION CHAT INITIALIZATION
// ========================================================
function initTelehealthChat(form) {
    const chatViewport = document.getElementById('chat-viewport');
    const textarea = document.getElementById('answer');
    const voiceTrigger = document.getElementById('voice-trigger');
    const dictationStatus = document.getElementById('dictation-status');
    const quickChips = document.querySelectorAll('.quick-chip-btn');
    const typingIndicator = document.getElementById('doctor-typing-indicator');

    // 1. Auto-scroll viewport to the bottom on load
    if (chatViewport) {
        chatViewport.scrollTop = chatViewport.scrollHeight;
    }

    // 2. Auto-growing Textarea
    if (textarea) {
        textarea.addEventListener('input', () => {
            textarea.style.height = 'auto';
            textarea.style.height = (textarea.scrollHeight) + 'px';
        });
        
        // Enter key to submit, Shift+Enter for newline
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (textarea.value.trim()) {
                    form.submit();
                }
            }
        });
    }

    // 3. Quick Suggestion Chips click mapping
    quickChips.forEach(chip => {
        chip.addEventListener('click', () => {
            if (textarea) {
                textarea.value = chip.getAttribute('data-value');
                textarea.focus();
                // Trigger auto-grow
                textarea.style.height = 'auto';
                textarea.style.height = (textarea.scrollHeight) + 'px';
                
                // Elastic bounce animation on chip for physical feedback
                gsap.fromTo(chip, { scale: 0.9 }, { scale: 1, duration: 0.3, ease: 'back.out(2)' });
            }
        });
    });

    // 4. Voice Dictation Integration (Web Speech API)
    if (voiceTrigger && textarea) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        
        if (SpeechRecognition) {
            const recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
            recognition.lang = 'en-US';

            let isListening = false;

            voiceTrigger.addEventListener('click', () => {
                if (!isListening) {
                    recognition.start();
                } else {
                    recognition.stop();
                }
            });

            recognition.onstart = () => {
                isListening = true;
                voiceTrigger.classList.add('mic-active');
                if (dictationStatus) dictationStatus.classList.remove('hidden');
                
                // Pulse animation using GSAP on mic button
                gsap.to(voiceTrigger, { scale: 1.15, repeat: -1, yoyo: true, duration: 0.6, ease: 'power1.inOut' });
            };

            recognition.onresult = (event) => {
                const transcript = event.results[0][0].transcript;
                if (textarea.value.trim()) {
                    textarea.value += ' ' + transcript;
                } else {
                    textarea.value = transcript;
                }
                
                // Trigger textarea auto-grow
                textarea.style.height = 'auto';
                textarea.style.height = (textarea.scrollHeight) + 'px';
            };

            recognition.onerror = (e) => {
                console.error("Speech recognition error:", e);
                stopListening();
            };

            recognition.onend = () => {
                stopListening();
            };

            function stopListening() {
                isListening = false;
                voiceTrigger.classList.remove('mic-active');
                if (dictationStatus) dictationStatus.classList.add('hidden');
                
                // Cancel GSAP scale animation
                gsap.killTweensOf(voiceTrigger);
                gsap.to(voiceTrigger, { scale: 1, duration: 0.3, ease: 'power2.out' });
                textarea.focus();
            }
        } else {
            // Hide or disable mic if browser doesn't support Web Speech API
            voiceTrigger.style.opacity = '0.4';
            voiceTrigger.title = 'Speech-to-Text not supported in this browser';
            voiceTrigger.addEventListener('click', () => {
                alert('Voice dictation is supported in Chrome, Safari, and Edge. Please use a modern browser for voice support.');
            });
        }
    }

    // 5. Entrance GSAP Animation for Chat Bubbles
    const chatRows = document.querySelectorAll('.chat-bubble-row');
    if (chatRows.length > 0) {
        // Animate the last couple of rows to make the feed feel alive
        const animateRows = Array.from(chatRows).slice(-3);
        gsap.fromTo(animateRows, 
            { opacity: 0, y: 30, scale: 0.95 },
            { opacity: 1, y: 0, scale: 1, duration: 0.6, stagger: 0.15, ease: 'power3.out' }
        );
    }

    // On submit: show patient answer in chat first, then "Dr AI is thinking"
    form.addEventListener('submit', (e) => {
        const answerText = textarea ? textarea.value.trim() : '';
        if (!answerText) {
            e.preventDefault();
            return;
        }

        e.preventDefault();

        const chatFeed = chatViewport ? chatViewport.querySelector('.chat-history-feed') : null;
        const patientInitial = form.dataset.patientInitial || 'P';
        const submitBtn = document.getElementById('submit-btn');

        if (chatFeed && typingIndicator) {
            const patientRow = document.createElement('div');
            patientRow.className = 'chat-bubble-row patient-row';
            patientRow.innerHTML = `
                <div class="chat-bubble-premium patient-bubble-premium">
                    <span class="chat-sender-badge">PATIENT (YOU)</span>
                    <div class="bubble-content-premium">${escapeHtml(answerText)}</div>
                </div>
                <div class="chat-avatar-mini patient-avatar-mini">${escapeHtml(patientInitial)}</div>
            `;
            chatFeed.insertBefore(patientRow, typingIndicator);

            gsap.fromTo(patientRow,
                { opacity: 0, y: 20, scale: 0.97 },
                { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: 'power2.out' }
            );

            chatViewport.scrollTop = chatViewport.scrollHeight;

            setTimeout(() => {
                typingIndicator.classList.remove('hidden');
                chatViewport.scrollTop = chatViewport.scrollHeight;
                if (submitBtn) {
                    submitBtn.disabled = true;
                    submitBtn.style.opacity = '0.5';
                }
                form.submit();
            }, 450);
        } else {
            if (submitBtn) {
                submitBtn.disabled = true;
                submitBtn.style.opacity = '0.5';
            }
            form.submit();
        }
    });
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
