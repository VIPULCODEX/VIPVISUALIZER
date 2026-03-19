document.addEventListener('DOMContentLoaded', () => {
    const btnLoad = document.getElementById('loadGraphBtn');
    const loader = document.querySelector('.loader');
    const btnText = document.querySelector('.btn-text');
    
    // UI Elements
    const elNodeCount = document.getElementById('nodeCount');
    const elEdgeCount = document.getElementById('edgeCount');
    const elCycleCount = document.getElementById('cycleCount');
    const elTimeInduced = document.getElementById('timeInduced');
    const elTimeAcyclic = document.getElementById('timeAcyclic');
    const elCycleList = document.getElementById('cycleList');
    const elConclusions = document.getElementById('benchmarkConclusion');
    const placeholder = document.querySelector('.placeholder-text');

    let network = null;
    let nodesDataset = new vis.DataSet();
    let edgesDataset = new vis.DataSet();
    
    let cyclesData = [];

    // Blood type colors
    const bloodColors = {
        'O': '#f78166',
        'A': '#58a6ff',
        'B': '#3fb950',
        'AB': '#bc8cff'
    };

    function initNetwork() {
        const container = document.getElementById('networkMap');
        const data = {
            nodes: nodesDataset,
            edges: edgesDataset
        };
        const options = {
            nodes: {
                shape: 'dot',
                size: 20,
                font: {
                    color: '#c9d1d9',
                    face: 'Inter',
                    size: 12
                },
                borderWidth: 2,
                shadow: true
            },
            edges: {
                width: 1.5,
                color: { color: 'rgba(255,255,255,0.2)' },
                arrows: {
                    to: { enabled: true, scaleFactor: 0.5 }
                },
                smooth: { type: 'continuous' }
            },
            physics: {
                forceAtlas2Based: {
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 100,
                    springConstant: 0.08
                },
                maxVelocity: 50,
                solver: 'forceAtlas2Based',
                timestep: 0.35,
                stabilization: { iterations: 150 }
            },
            interaction: {
                hover: true,
                tooltipDelay: 200
            }
        };
        network = new vis.Network(container, data, options);
    }

    initNetwork();

    btnLoad.addEventListener('click', async () => {
        // loading state
        btnLoad.disabled = true;
        btnText.textContent = "Processing...";
        loader.classList.remove('hidden');
        placeholder.style.display = 'none';

        const numNodes = document.getElementById('nodeInput').value || 50;

        try {
            // Trigger backend load with node count
            const resLoad = await fetch(`/api/load?nodes=${numNodes}`);
            const dataLoad = await resLoad.json();

            if(dataLoad.success) {
                // Fetch graph + cycles
                await Promise.all([fetchGraph(), fetchCycles()]);
            } else {
                alert("Failed to load generic data");
            }

        } catch(e) {
            console.error(e);
            alert("Error loading graph data.");
        } finally {
            btnLoad.disabled = false;
            btnText.textContent = "Load Patient Graph";
            loader.classList.add('hidden');
        }
    });

    async function fetchGraph() {
        const res = await fetch('/api/graph');
        const data = await res.json();
        
        elNodeCount.textContent = data.nodes.length;
        elEdgeCount.textContent = data.edges.length;

        // format visual nodes
        const visNodes = data.nodes.map(n => ({
            id: n.id,
            label: n.id,
            title: `Patient: ${n.id}<br>Donor: ${n.donor_bg}<br>Recipient: ${n.recipient_bg}`,
            color: {
                background: bloodColors[n.donor_bg] || '#555',
                border: '#ffffff'
            }
        }));

        nodesDataset.clear();
        edgesDataset.clear();
        nodesDataset.add(visNodes);
        edgesDataset.add(data.edges);
    }

    async function fetchCycles() {
        const res = await fetch('/api/cycles');
        const data = await res.json();
        
        elCycleCount.textContent = data.count;
        elTimeInduced.textContent = `${data.total_induced_time_ms.toFixed(2)} ms`;
        elTimeAcyclic.textContent = `${data.total_acyclic_time_ms.toFixed(2)} ms`;
        
        cyclesData = data.cycles;
        
        elCycleList.innerHTML = '';
        if (cyclesData.length === 0) {
            elCycleList.innerHTML = '<li class="empty-state">No cycles found ≤ 3 length</li>';
        } else {
            cyclesData.forEach((c, idx) => {
                const li = document.createElement('li');
                li.innerHTML = `<strong>Cycle ${idx+1}:</strong> ${c.cycle.join(' → ')}`;
                li.addEventListener('click', () => highlightCycle(c.cycle));
                elCycleList.appendChild(li);
            });
        }

        // Conclusion
        if(data.count > 0) {
            elConclusions.style.display = 'block';
            if(data.total_acyclic_time_ms < data.total_induced_time_ms) {
                elConclusions.innerHTML = `The <strong>Acyclic Matching</strong> check ran <strong>faster</strong> than Induced Matching for this batch!`;
                elConclusions.style.color = 'var(--accent-green)';
            } else {
                elConclusions.innerHTML = `The <strong>Induced Matching</strong> check ran <strong>faster</strong> than Acyclic Matching for this batch!`;
                elConclusions.style.color = 'var(--accent-blue)';
            }
        }
    }

    function highlightCycle(cycleNodes) {
        // Reset edges
        const allEdges = edgesDataset.get();
        const resetEdges = allEdges.map(e => ({...e, color: { color: 'rgba(255,255,255,0.2)' }, width: 1.5 }));
        edgesDataset.update(resetEdges);
        
        // Find edges inside cycle
        let cycleEdges = [];
        for(let i=0; i<cycleNodes.length; i++) {
            let u = cycleNodes[i];
            let v = cycleNodes[(i+1)%cycleNodes.length];
            // find edge ID in vis.js
            let edge = allEdges.find(e => e.from === u && e.to === v);
            if(edge) {
                cycleEdges.push({id: edge.id, color: { color: '#bc8cff' }, width: 3});
            }
        }
        edgesDataset.update(cycleEdges);

        // Focus network
        if(network) {
            network.fit({
                nodes: cycleNodes,
                animation: { duration: 1000, easingFunction: "easeInOutQuad" }
            });
        }
    }
});
