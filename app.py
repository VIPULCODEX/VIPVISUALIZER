# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

from flask import Flask, jsonify, render_template, request
import os
from kidney_exchange import KidneyExchange, MIAMSolver, PSKCPSolver

app = Flask(__name__)

# ── In-memory cache ──────────────────────────────────────────
_cache = {
    'graph':  None,   # {nodes, edges}
    'cycles': None,   # {cycles, count, times}
    'kx':     None,   # KidneyExchange instance (kept for MIAM)
}


@app.route('/')
def index():
    return render_template('index.html')


# ── Load dataset & build graph ───────────────────────────────
@app.route('/api/load')
def load_data():
    num_nodes = request.args.get('nodes', default=50, type=int)
    csv_path  = os.path.join(os.path.dirname(__file__),
                             'Kidney_Organ_SupplyChain_RawDataset.csv')

    kx = KidneyExchange()
    if not kx.load_from_csv(csv_path, max_rows=num_nodes):
        return jsonify({'error': 'Failed to load CSV'})

    kx.build_graph()
    _cache['kx'] = kx   # keep reference for MIAM

    # Graph payload
    nodes = [
        {
            'id':           k,
            'label':        f"{k} ({v['donor']}→{v['recipient']})",
            'donor_bg':     v['donor'],
            'recipient_bg': v['recipient'],
        }
        for k, v in kx.nodes.items()
    ]
    edges = [
        {'from': u, 'to': v}
        for u, nbrs in kx.adj_list.items()
        for v in nbrs
    ]
    _cache['graph'] = {'nodes': nodes, 'edges': edges}

    # Cycle analysis
    cycles           = kx.find_cycles(max_length=3)
    total_t_induced  = 0
    total_t_acyclic  = 0
    cycle_results    = []

    for cycle in cycles:
        matching              = kx.extract_matching(cycle)
        is_ind, t_ind         = kx.is_induced_matching(cycle)
        is_acy, t_acy         = kx.is_acyclic_matching(matching)
        total_t_induced      += t_ind
        total_t_acyclic      += t_acy
        cycle_results.append({
            'cycle':           cycle,
            'matching':        matching,
            'is_induced':      is_ind,
            'time_induced_ms': t_ind * 1000,
            'is_acyclic':      is_acy,
            'time_acyclic_ms': t_acy * 1000,
        })

    _cache['cycles'] = {
        'cycles':               cycle_results,
        'count':                len(cycles),
        'total_induced_time_ms': total_t_induced * 1000,
        'total_acyclic_time_ms': total_t_acyclic * 1000,
    }

    return jsonify({'success': True})


@app.route('/api/graph')
def get_graph():
    return jsonify(_cache['graph'] or {'nodes': [], 'edges': []})


@app.route('/api/cycles')
def get_cycles():
    return jsonify(_cache['cycles'] or {'cycles': [], 'count': 0})


# ── NEW: Run MIAM algorithm ───────────────────────────────────
@app.route('/api/miam')
def run_miam():
    """
    Run the full MIAM pipeline:
      1. Build conflict graph C (hospital/crossmatch resource simulation)
      2. Assign weights (blood-type rarity + urgency proxy)
      3. Kernelise with 3 weighted reduction rules
      4. Run greedy baseline  (O(n²))
      5. Run FPT algorithm    (O(2^k · n) on kernel)
      6. Return comparison + conflict edges for frontend visualisation
    """
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})

    num_hospitals = request.args.get('hospitals', default=6, type=int)

    solver = MIAMSolver(_cache['kx'])
    result = solver.run(num_hospitals=num_hospitals)
    return jsonify(result)


@app.route('/api/pskcp')
def run_pskcp():
    """
    Run Preference-Stable Kernelized Cycle Packing:
      1. Generate 2/3-cycle exchange candidates
      2. Score candidates using dataset-derived recipient preference proxies
      3. Build a conflict graph over candidate cycles
      4. Reduce the candidate graph with practical kernel rules
      5. Compare greedy cycle packing with FPT branch-and-bound on the kernel
    """
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})

    max_candidates = request.args.get('max_candidates', default=350, type=int)
    max_length = request.args.get('max_length', default=3, type=int)
    num_hospitals = request.args.get('hospitals', default=6, type=int)
    top_per_patient = request.args.get('top_per_patient', default=12, type=int)

    solver = PSKCPSolver(_cache['kx'])
    result = solver.run(
        max_length=min(max(max_length, 2), 3),
        max_candidates=min(max(max_candidates, 25), 1000),
        num_hospitals=min(max(num_hospitals, 1), 25),
        top_per_patient=min(max(top_per_patient, 3), 30),
    )
    return jsonify(result)


if __name__ == '__main__':
    app.run(debug=True, port=5000)
