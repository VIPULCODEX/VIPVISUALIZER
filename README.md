# VIPvisualize — Kidney Exchange Graph Simulator

> **A Conflict-Free Kidney Exchange Algorithm via Mixed Induced-Acyclic Matching (MIAM)**  
> Minor Project | Parameterized Complexity Research

[![Live Demo](https://img.shields.io/badge/Live%20Demo-vipvisualizer.onrender.com-blue?style=for-the-badge&logo=render)](https://vipvisualizer.onrender.com)
[![Python](https://img.shields.io/badge/Python-3.11-blue?style=flat-square&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.x-black?style=flat-square&logo=flask)](https://flask.palletsprojects.com)

---

## 🌐 Live Demo

**[https://vipvisualizer.onrender.com](https://vipvisualizer.onrender.com)**

> ⚠️ Hosted on Render free tier — app may take ~30 seconds to wake up on first visit.

---

## 📌 About

This project implements and visualizes the **Mixed Induced-Acyclic Matching (MIAM)** algorithm applied to Kidney Exchange Programs (KEP).

Standard KEP solvers find cycles and chains using Integer Linear Programming but ignore **conflict relationships** between exchanges (shared crossmatch labs, surgical team constraints, tissue type overlaps). This project introduces a new model:

- **Compatibility Graph G** — directed edges where donor blood type of pair `u` is compatible with recipient blood type of pair `v`
- **Conflict Graph C** — edges between pairs that share a hospital/crossmatch resource (cannot both be activated)
- **MIAM** — maximum weight set of exchanges satisfying induced + conflict-free + acyclic constraints simultaneously
- **PS-KCP** — preference-stable kernelized cycle packing over real 2-cycle and 3-cycle exchange candidates

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔬 **MIAM Algorithm** | FPT algorithm with weighted kernelisation + bounded search tree |
| **PS-KCP Hybrid** | Preference-stable cycle packing with greedy seed + kernelized FPT search |
| 🧠 **Kernelisation** | 3 reduction rules (isolated removal, forced inclusion, dominated vertex) |
| ⚡ **Greedy Baseline** | O(n²) greedy MIAM for comparison |
| 📊 **Algorithm Benchmark** | Induced vs Acyclic matching time comparison across all cycles |
| 🕸️ **Graph Visualisation** | Interactive vis-network graph with blood-type colour coding |
| ⚔️ **Conflict Overlay** | Toggle dashed red conflict edges on the compatibility graph |
| 🏅 **MIAM Highlight** | Gold-bordered nodes show the optimal MIAM solution |
| 🎨 **Premium Dark UI** | Glassmorphism sidebar, animated particle background, JetBrains Mono stats |

---

## 🧠 Algorithm Details

### Preference-Stable Kernelized Cycle Packing (PS-KCP)

PS-KCP is the newer hybrid approach in this project. It works at the exchange-cycle level rather than selecting individual patient-pair vertices:

1. Generate valid 2-cycle and 3-cycle kidney exchange candidates from the compatibility graph.
2. Score each candidate using dataset-derived preference proxies: predicted survival chance, organ health score, diagnosis urgency, donor approval, donor age/weight fit, and blood-type compatibility.
3. Build a conflict graph between cycle candidates when they share patient pairs or simulated hospital/crossmatch resources.
4. Apply practical kernel rules: remove duplicate/dominated cycles, cap low-ranked patient-local alternatives, and force isolated safe cycles.
5. Compare a greedy cycle-packing seed with FPT branch-and-bound on the reduced candidate graph.
6. Count blocking cycles as a stability proxy: an unselected cycle blocks if every involved recipient would prefer that cycle's donor over their current assignment.

This does not claim to beat NP-hardness. The practical claim is that preprocessing reduces the effective candidate graph before exact search on small and medium bounded-cycle kidney exchange instances.

### Mixed Induced-Acyclic Matching (MIAM)

A set **S** of donor-recipient pairs is a valid MIAM if:
1. **S** is an independent set in **G** (no direct compatibility edge between selected pairs)
2. **S** is an independent set in **C** (no resource conflict between selected pairs)
3. The exchange subgraph induced by **S** is acyclic

### Weighted Kernelisation (3 Reduction Rules)

| Rule | Description | Effect |
|------|-------------|--------|
| **Rule 1** | Remove isolated vertices (degree 0 in both G and C) | Shrinks graph |
| **Rule 2** | Force-include vertices with no conflict neighbours | Fixes part of the solution |
| **Rule 3** | Remove dominated vertices (lower weight + subset of neighbours) | Reduces branching |

**Result:** Kernel of size O(k), from which the FPT algorithm runs in O(2^k · n).

### Weight Function
```
w(v) = blood_type_rarity_score(donor, recipient) + urgency_proxy(patient_id)
```
- O→AB donor pairs score highest (rarest compatibility)
- Urgency is simulated from patient ID hash (1–3)

---

## 🗂️ Project Structure

```
VIPVISUALIZER/
├── app.py                              # Flask backend API endpoints
├── kidney_exchange.py                  # KidneyExchange, MIAMSolver, PSKCPSolver
├── Kidney_Organ_SupplyChain_RawDataset.csv  # Real dataset (2000+ pairs)
├── templates/
│   └── index.html                      # Frontend HTML
├── static/
│   ├── style.css                       # Premium dark UI CSS
│   └── script.js                       # Vis-network + MIAM/PS-KCP frontend logic
├── Procfile                            # Render/gunicorn start command
├── render.yaml                         # Render one-click deploy blueprint
└── requirements.txt                    # Flask, pandas, gunicorn
```

---

## 🚀 API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Serve the main UI |
| `GET /api/load?nodes=N` | Load N rows from CSV, build graph, find cycles |
| `GET /api/graph` | Return graph nodes + edges (cached) |
| `GET /api/cycles` | Return cycles + induced/acyclic benchmark times |
| `GET /api/miam` | Run full MIAM pipeline (conflict graph + greedy + FPT) |
| `GET /api/pskcp` | Run PS-KCP hybrid cycle packing with preference/stability scoring |

---

## 🛠️ Local Setup

```bash
git clone https://github.com/VIPULCODEX/VIPVISUALIZER.git
cd VIPVISUALIZER
pip install -r requirements.txt
python app.py
```
Open [http://localhost:5000](http://localhost:5000)

---

## 📚 Research Background

Based on the paper:
> *"The Parameterized Complexity of the Induced Matching Problem"*  
> Hannes Moser and Somnath Sikdar

Key results applied:
- Linear kernel on bounded-degree graphs (kidney graphs have max degree ≤ 6 by blood type structure)
- FPT algorithm via kernelisation + bounded search tree
- W[1]-hardness on general bipartite graphs (justifies restricting to kidney graph structure)

---

*© First Placement by Vipul Sharma*
