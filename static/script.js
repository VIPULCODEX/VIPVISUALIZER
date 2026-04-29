/* ============================================================
   VIPvisualize — Premium JavaScript
   Author: Vipul Sharma
   ============================================================ */

document.addEventListener('DOMContentLoaded', () => {

    // ── Background Canvas Animation ────────────────────────────
    const canvas = document.getElementById('bgCanvas');
    const ctx = canvas.getContext('2d');

    let W, H, particles = [];

    function resizeCanvas() {
        W = canvas.width  = window.innerWidth;
        H = canvas.height = window.innerHeight;
    }

    function createParticles() {
        particles = [];
        const count = Math.floor((W * H) / 18000);
        for (let i = 0; i < count; i++) {
            particles.push({
                x: Math.random() * W,
                y: Math.random() * H,
                vx: (Math.random() - 0.5) * 0.3,
                vy: (Math.random() - 0.5) * 0.3,
                r:  Math.random() * 1.5 + 0.5,
                alpha: Math.random() * 0.4 + 0.1
            });
        }
    }

    function drawBg() {
        ctx.clearRect(0, 0, W, H);
        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < 120) {
                    ctx.beginPath();
                    ctx.strokeStyle = `rgba(88,166,255,${0.08 * (1 - dist / 120)})`;
                    ctx.lineWidth = 0.6;
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
        // Draw nodes
        for (const p of particles) {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(88,166,255,${p.alpha})`;
            ctx.fill();
            p.x += p.vx;
            p.y += p.vy;
            if (p.x < 0 || p.x > W) p.vx *= -1;
            if (p.y < 0 || p.y > H) p.vy *= -1;
        }
        requestAnimationFrame(drawBg);
    }

    resizeCanvas();
    createParticles();
    drawBg();
    window.addEventListener('resize', () => { resizeCanvas(); createParticles(); });


    // ── DOM References ─────────────────────────────────────────
    const btnLoad        = document.getElementById('loadGraphBtn');
    const btnText        = document.getElementById('btnText');
    const btnLoader      = document.getElementById('btnLoader');
    const btnIcon        = document.querySelector('.btn-icon');

    const elNodeCount    = document.getElementById('nodeCount');
    const elEdgeCount    = document.getElementById('edgeCount');
    const elCycleCount   = document.getElementById('cycleCount');
    const elTimeInduced  = document.getElementById('timeInduced');
    const elTimeAcyclic  = document.getElementById('timeAcyclic');
    const elCycleList    = document.getElementById('cycleList');
    const cycleBadge     = document.getElementById('cycleBadge');
    const conclusionBox  = document.getElementById('conclusionBox');
    const conclusionText = document.getElementById('benchmarkConclusion');
    const barInduced     = document.getElementById('barInduced');
    const barAcyclic     = document.getElementById('barAcyclic');
    const hudStatus      = document.getElementById('hudStatus');
    const selectedCycleInfo = document.getElementById('selectedCycleInfo');
    const selectedCycleText = document.getElementById('selectedCycleText');
    const graphPlaceholder  = document.getElementById('graphPlaceholder');


    // ── vis-network Setup ──────────────────────────────────────
    let network       = null;
    let nodesDataset  = new vis.DataSet();
    let edgesDataset  = new vis.DataSet();
    let cyclesData    = [];
    let activeIdx     = -1;

    const bloodColors = {
        'O':  '#f78166',
        'A':  '#58a6ff',
        'B':  '#3fb950',
        'AB': '#bc8cff'
    };

    function initNetwork() {
        const container = document.getElementById('networkMap');
        const data    = { nodes: nodesDataset, edges: edgesDataset };
        const options = {
            nodes: {
                shape: 'dot',
                size: 14,
                font: {
                    color: 'rgba(230,237,243,0.85)',
                    face: 'Inter',
                    size: 11,
                    strokeWidth: 2,
                    strokeColor: 'rgba(0,0,0,0.6)'
                },
                borderWidth: 1.5,
                borderWidthSelected: 3,
                shadow: { enabled: true, size: 12, x: 0, y: 0 }
            },
            edges: {
                width: 1,
                color: { color: 'rgba(255,255,255,0.08)', highlight: '#f0c060', hover: 'rgba(255,255,255,0.25)' },
                arrows: { to: { enabled: true, scaleFactor: 0.4, type: 'arrow' } },
                smooth: { type: 'curvedCW', roundness: 0.1 },
                selectionWidth: 2
            },
            physics: {
                forceAtlas2Based: {
                    gravitationalConstant: -55,
                    centralGravity: 0.008,
                    springLength: 110,
                    springConstant: 0.07,
                    damping: 0.4
                },
                maxVelocity: 80,
                solver: 'forceAtlas2Based',
                timestep: 0.35,
                stabilization: { iterations: 200, updateInterval: 25 }
            },
            interaction: {
                hover: true,
                tooltipDelay: 150,
                hideEdgesOnDrag: true,
                navigationButtons: false,
                keyboard: false
            }
        };
        network = new vis.Network(container, data, options);
    }

    initNetwork();


    // ── Load Button ────────────────────────────────────────────
    btnLoad.addEventListener('click', async () => {
        const numNodes = parseInt(document.getElementById('nodeInput').value) || 50;

        // Loading state
        btnLoad.disabled = true;
        btnText.textContent = 'Analysing…';
        btnLoader.classList.remove('hidden');
        btnIcon.classList.add('hidden');
        graphPlaceholder.style.display = 'none';
        hudStatus.textContent = 'Loading dataset…';

        try {
            const resLoad = await fetch(`/api/load?nodes=${numNodes}`);
            const dataLoad = await resLoad.json();

            if (dataLoad.success) {
                hudStatus.textContent = 'Building graph…';
                await Promise.all([fetchGraph(), fetchCycles()]);
                hudStatus.textContent = `Graph loaded — ${numNodes} patients visualised`;
                enableMiam();  // unlock MIAM button after successful load
            } else {
                hudStatus.textContent = 'Error loading data';
                alert('Failed to load dataset from server.');
            }
        } catch (e) {
            console.error(e);
            hudStatus.textContent = 'Network error';
            alert('Could not reach the server. Is Flask running?');
        } finally {
            btnLoad.disabled = false;
            btnText.textContent = 'Reload Graph';
            btnLoader.classList.add('hidden');
            btnIcon.classList.remove('hidden');
        }
    });


    // ── Fetch Graph ────────────────────────────────────────────
    async function fetchGraph() {
        const res  = await fetch('/api/graph');
        const data = await res.json();

        animateValue(elNodeCount, data.nodes.length);
        animateValue(elEdgeCount, data.edges.length);

        const visNodes = data.nodes.map(n => ({
            id: n.id,
            label: n.id,
            title: `<div style="font-family:Inter,sans-serif;font-size:12px;padding:4px 0">
                        <b style="color:#e6edf3">${n.id}</b><br>
                        <span style="color:#7d8590">Donor: </span><b style="color:${bloodColors[n.donor_bg] || '#fff'}">${n.donor_bg}</b><br>
                        <span style="color:#7d8590">Recipient: </span><b style="color:${bloodColors[n.recipient_bg] || '#fff'}">${n.recipient_bg}</b>
                    </div>`,
            color: {
                background: bloodColors[n.donor_bg] || '#4a5060',
                border: 'rgba(255,255,255,0.2)',
                highlight: { background: '#f0c060', border: '#f0c060' },
                hover: { background: bloodColors[n.donor_bg] || '#4a5060', border: 'rgba(255,255,255,0.6)' }
            },
            shadow: { color: bloodColors[n.donor_bg] || '#4a5060' }
        }));

        nodesDataset.clear();
        edgesDataset.clear();
        nodesDataset.add(visNodes);
        edgesDataset.add(data.edges);
    }


    // ── Fetch Cycles ───────────────────────────────────────────
    async function fetchCycles() {
        const res  = await fetch('/api/cycles');
        const data = await res.json();

        const count = data.count || 0;
        animateValue(elCycleCount, count);
        cycleBadge.textContent = count;

        const tInd = (data.total_induced_time_ms || 0).toFixed(3);
        const tAcy = (data.total_acyclic_time_ms || 0).toFixed(3);
        elTimeInduced.textContent = `${tInd} ms`;
        elTimeAcyclic.textContent = `${tAcy} ms`;

        // Animated bars (relative)
        const maxT = Math.max(parseFloat(tInd), parseFloat(tAcy), 0.001);
        setTimeout(() => {
            barInduced.style.width = `${(parseFloat(tInd) / maxT * 100).toFixed(1)}%`;
            barAcyclic.style.width = `${(parseFloat(tAcy) / maxT * 100).toFixed(1)}%`;
        }, 200);

        // Conclusion
        if (count > 0) {
            conclusionBox.classList.remove('hidden', 'winner-blue', 'winner-purple');
            if (parseFloat(tAcy) < parseFloat(tInd)) {
                conclusionBox.classList.add('winner-purple');
                conclusionText.innerHTML = `🏆 <strong>Acyclic Matching</strong> was faster — Δ ${(parseFloat(tInd) - parseFloat(tAcy)).toFixed(3)} ms`;
            } else {
                conclusionBox.classList.add('winner-blue');
                conclusionText.innerHTML = `🏆 <strong>Induced Matching</strong> was faster — Δ ${(parseFloat(tAcy) - parseFloat(tInd)).toFixed(3)} ms`;
            }
        }

        // Cycle List
        cyclesData = data.cycles || [];
        elCycleList.innerHTML = '';
        activeIdx = -1;

        if (cyclesData.length === 0) {
            elCycleList.innerHTML = '<li class="cycle-empty">No exchange cycles of length ≤ 3 found</li>';
        } else {
            cyclesData.forEach((c, idx) => {
                const li = document.createElement('li');
                li.innerHTML = `<span class="cycle-num">#${idx + 1}</span>${c.cycle.join(' → ')}`;
                li.addEventListener('click', () => highlightCycle(c.cycle, idx, li));
                elCycleList.appendChild(li);
            });
        }
    }


    // ── Highlight a Cycle ──────────────────────────────────────
    function highlightCycle(cycleNodes, idx, el) {
        // Deactivate old
        document.querySelectorAll('.cycle-list li').forEach(li => li.classList.remove('active'));

        if (activeIdx === idx) {
            // Toggle off
            activeIdx = -1;
            resetEdgeColors();
            selectedCycleInfo.style.display = 'none';
            return;
        }

        activeIdx = idx;
        el.classList.add('active');

        // Reset all edges
        resetEdgeColors();

        // Highlight cycle edges
        const allEdges = edgesDataset.get();
        const updates  = [];
        for (let i = 0; i < cycleNodes.length; i++) {
            const u = cycleNodes[i];
            const v = cycleNodes[(i + 1) % cycleNodes.length];
            const edge = allEdges.find(e => e.from === u && e.to === v);
            if (edge) {
                updates.push({
                    id: edge.id,
                    color: { color: '#f0c060', highlight: '#f0c060' },
                    width: 3,
                    shadow: { enabled: true, color: '#f0c060', size: 12 }
                });
            }
        }
        edgesDataset.update(updates);

        // Focus network
        network.fit({
            nodes: cycleNodes,
            animation: { duration: 800, easingFunction: 'easeInOutCubic' }
        });

        // HUD update
        selectedCycleInfo.style.display = 'flex';
        selectedCycleText.textContent = `Cycle #${idx + 1}: ${cycleNodes.join(' → ')}`;
    }

    function resetEdgeColors() {
        const allEdges = edgesDataset.get();
        edgesDataset.update(allEdges.map(e => ({
            ...e,
            color: { color: 'rgba(255,255,255,0.08)', highlight: '#f0c060', hover: 'rgba(255,255,255,0.25)' },
            width: 1,
            shadow: { enabled: false }
        })));
    }


    // ── Utility: Animate number ────────────────────────────────
    function animateValue(el, target) {
        el.classList.remove('animate');
        void el.offsetWidth; // reflow
        el.classList.add('animate');
        el.textContent = target;
    }


    // ══════════════════════════════════════════════════════════
    //  MIAM Algorithm Integration
    // ══════════════════════════════════════════════════════════

    const runMiamBtn      = document.getElementById('runMiamBtn');
    const miamBtnText     = document.getElementById('miamBtnText');
    const miamLoader      = document.getElementById('miamLoader');
    const miamStats       = document.getElementById('miamStats');
    const miamCompare     = document.getElementById('miamCompare');
    const miamVerdict     = document.getElementById('miamVerdict');
    const toggleConflicts = document.getElementById('toggleConflicts');

    let conflictEdgesData  = [];   // raw {from,to} list from API
    let conflictEdgesVis   = [];   // vis edge IDs added to the graph
    let showingConflicts   = false;
    let miamSolutionNodes  = [];   // nodes in FPT MIAM solution

    // Enable the MIAM button once the graph is loaded
    function enableMiam() {
        runMiamBtn.disabled    = false;
        miamBtnText.textContent = 'Run MIAM Algorithm';
    }

    // Call enableMiam after successful graph load
    const _origLoad = btnLoad.onclick;
    btnLoad.addEventListener('click', () => {
        // Will be enabled after fetchCycles resolves (hooked below)
    });

    // ── Run MIAM ──────────────────────────────────────────────
    runMiamBtn.addEventListener('click', async () => {
        runMiamBtn.disabled     = true;
        miamBtnText.textContent = 'Computing…';
        miamLoader.classList.remove('hidden');
        hudStatus.textContent   = 'Running MIAM algorithm…';

        try {
            const res  = await fetch('/api/miam');
            const data = await res.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            renderMiamResults(data);
            hudStatus.textContent = `MIAM complete — FPT solution: ${data.fpt.size} pairs, weight ${data.fpt.weight}`;

        } catch (e) {
            console.error(e);
            hudStatus.textContent = 'MIAM error';
        } finally {
            runMiamBtn.disabled     = false;
            miamBtnText.textContent = 'Re-run MIAM';
            miamLoader.classList.add('hidden');
        }
    });

    // ── Render MIAM results ───────────────────────────────────
    function renderMiamResults(data) {
        const { greedy, fpt, n_conflict_edges, conflict_edges } = data;

        // Save conflict edges for toggle
        conflictEdgesData = conflict_edges || [];

        // Stats panel
        document.getElementById('miamConflicts').textContent = n_conflict_edges;
        document.getElementById('miamKernel').textContent    = fpt.kernel_size + ' nodes';
        document.getElementById('miamReduction').textContent = fpt.kernel_reduction + '%';
        miamStats.classList.remove('hidden');

        // Comparison table
        document.getElementById('cmpGreedySize').textContent = greedy.size;
        document.getElementById('cmpFptSize').textContent    = fpt.size;
        document.getElementById('cmpGreedyW').textContent    = greedy.weight;
        document.getElementById('cmpFptW').textContent       = fpt.weight;
        document.getElementById('cmpGreedyT').textContent    = greedy.time_ms + ' ms';
        document.getElementById('cmpFptT').textContent       = fpt.time_ms + ' ms';
        miamCompare.classList.remove('hidden');

        // Verdict
        miamVerdict.classList.remove('hidden');
        const weightDiff = data.weight_improvement;
        const sizeDiff   = data.size_improvement;
        if (weightDiff > 0) {
            miamVerdict.innerHTML =
                `🏆 <strong style="color:var(--purple)">FPT MIAM</strong> found a better solution: ` +
                `+${weightDiff} weight, +${sizeDiff} pairs vs greedy. ` +
                `Kernel reduced graph by <strong>${fpt.kernel_reduction}%</strong>.`;
        } else {
            miamVerdict.innerHTML =
                `Greedy matched FPT quality on this instance (common for small graphs). ` +
                `Kernel: <strong style="color:var(--gold)">${fpt.kernel_size}</strong> / ${fpt.original_size} nodes.`;
        }

        // Highlight MIAM solution nodes in the graph (orange glow)
        miamSolutionNodes = fpt.solution || [];
        highlightMiamNodes(miamSolutionNodes);

        // Show conflict toggle
        toggleConflicts.classList.remove('hidden');
    }

    // ── Highlight MIAM solution nodes ─────────────────────────
    function highlightMiamNodes(nodeIds) {
        const updates = [];
        nodesDataset.forEach(n => {
            if (nodeIds.includes(n.id)) {
                updates.push({
                    id: n.id,
                    borderWidth: 3,
                    color: {
                        background: n.color?.background || '#4a5060',
                        border: '#f0c060',
                        highlight: { background: '#f0c060', border: '#fff' }
                    },
                    shadow: { enabled: true, color: '#f0c060', size: 18 }
                });
            } else {
                updates.push({ id: n.id, borderWidth: 1.5,
                    shadow: { enabled: true, size: 6, color: n.color?.background || '#4a5060' }
                });
            }
        });
        nodesDataset.update(updates);
    }

    // ── Toggle conflict edges overlay ─────────────────────────
    toggleConflicts.addEventListener('click', () => {
        if (showingConflicts) {
            // Remove conflict edges
            edgesDataset.remove(conflictEdgesVis);
            conflictEdgesVis = [];
            showingConflicts = false;
            toggleConflicts.classList.remove('active');
            toggleConflicts.innerHTML = `
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                Show conflict edges`;
        } else {
            // Add conflict edges as dashed red
            const toAdd = conflictEdgesData.map((e, i) => ({
                id:     `conflict_${i}`,
                from:   e.from,
                to:     e.to,
                color:  { color: 'rgba(247,129,102,0.5)', highlight: '#f78166' },
                width:  1,
                dashes: [4, 4],
                arrows: { to: { enabled: false } },
                shadow: { enabled: false },
                title:  'Conflict edge (resource constraint)'
            }));
            edgesDataset.add(toAdd);
            conflictEdgesVis = toAdd.map(e => e.id);
            showingConflicts = true;
            toggleConflicts.classList.add('active');
            toggleConflicts.innerHTML = `
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                Hide conflict edges`;
        }
    });

});
