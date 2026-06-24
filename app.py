# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
import os
from kidney_exchange import KidneyExchange, MIAMSolver, PSKCPSolver, FormulationComparer

app = Flask(__name__)
MAX_INTERACTIVE_NODES = int(os.environ.get('MAX_INTERACTIVE_NODES', 256))
CYCLE_RESULT_LIMIT = int(os.environ.get('CYCLE_RESULT_LIMIT', 5000))

# ── In-memory cache ──────────────────────────────────────────
_cache = {
    'graph':  None,   # {nodes, edges}
    'cycles': None,   # {cycles, count, times}
    'kx':     None,   # KidneyExchange instance (kept for MIAM)
}


def _api_error(message, status=400):
    return jsonify({'success': False, 'error': message}), status


@app.errorhandler(Exception)
def handle_unexpected_error(exc):
    if request.path.startswith('/api/'):
        if isinstance(exc, HTTPException):
            return _api_error(exc.description, exc.code)
        app.logger.exception("Unhandled API error")
        return _api_error(str(exc), 500)
    if isinstance(exc, HTTPException):
        return exc
    app.logger.exception("Unhandled page error")
    raise exc


def _safe_dataset_id(dataset_id):
    return os.path.basename(dataset_id).replace('.wmd', '').replace('.dat', '')


def _preflib_metadata(wmd_path):
    meta = {'nodes': None, 'edges': None}
    try:
        with open(wmd_path, 'r') as f:
            for line in f:
                if line.startswith('# NUMBER ALTERNATIVES:'):
                    meta['nodes'] = int(line.split(':', 1)[1].strip())
                elif line.startswith('# NUMBER EDGES:'):
                    meta['edges'] = int(line.split(':', 1)[1].strip())
                elif not line.startswith('#'):
                    break
    except (OSError, ValueError):
        pass
    return meta


@app.route('/')
def index():
    return render_template('index.html')


# ── Load dataset & build graph ───────────────────────────────
@app.route('/api/datasets')
def list_datasets():
    ds_dir = os.path.join(os.path.dirname(__file__), 'dataset')
    if not os.path.exists(ds_dir):
        return jsonify({'datasets': []})
    files = os.listdir(ds_dir)
    datasets = []
    for filename in files:
        if not filename.endswith('.wmd'):
            continue
        dataset_id = filename[:-4]
        meta = _preflib_metadata(os.path.join(ds_dir, filename))
        node_count = meta.get('nodes') or 0
        if node_count and node_count > MAX_INTERACTIVE_NODES:
            continue
        datasets.append({
            'id': dataset_id,
            'nodes': meta.get('nodes'),
            'edges': meta.get('edges'),
            'label': f"{dataset_id} ({meta.get('nodes', '?')} nodes)",
        })
    datasets.sort(key=lambda item: (item.get('nodes') or 0, item['id']))
    return jsonify({'datasets': datasets, 'max_interactive_nodes': MAX_INTERACTIVE_NODES})


@app.route('/api/load')
def load_data():
    dataset_id = _safe_dataset_id(request.args.get('dataset_id', default='00036-00000001', type=str))
    
    kx = KidneyExchange()
    if dataset_id == 'csv':
        num_nodes = request.args.get('nodes', default=50, type=int)
        csv_path  = os.path.join(os.path.dirname(__file__),
                                 'Kidney_Organ_SupplyChain_RawDataset.csv')
        if not os.path.exists(csv_path):
            csv_path = os.path.join(os.path.dirname(__file__), 'dataset', 'Kidney_Organ_SupplyChain_RawDataset.csv')
        if not kx.load_from_csv(csv_path, max_rows=num_nodes):
            return jsonify({'error': 'Failed to load CSV'})
        kx.build_graph()
    else:
        ds_dir = os.path.join(os.path.dirname(__file__), 'dataset')
        base_path = os.path.join(ds_dir, dataset_id)
        wmd_path = base_path + '.wmd'
        if not os.path.exists(wmd_path):
            return _api_error(f'Dataset {dataset_id} was not found on the server.', 404)
        meta = _preflib_metadata(wmd_path)
        node_count = meta.get('nodes') or 0
        if node_count > MAX_INTERACTIVE_NODES:
            return _api_error(
                f'Dataset {dataset_id} has {node_count} nodes. '
                f'The web visualizer is capped at {MAX_INTERACTIVE_NODES} nodes to avoid Hugging Face request timeouts.',
                413,
            )
        if not kx.load_from_preflib(base_path):
            return _api_error(f'Failed to load PrefLib instance {dataset_id}', 500)
        # Note: load_from_preflib already builds the adjacency list based on .wmd file

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
    cycles           = kx.find_cycles(max_length=3, max_cycles=CYCLE_RESULT_LIMIT)
    total_t_induced  = 0
    total_t_acyclic  = 0
    cycle_results    = []

    for cycle in cycles:
        matching              = kx.extract_matching(cycle)
        
        # Optimization: Skip heavy matching checks on large instances
        if len(cycles) <= 100:
            is_ind, t_ind         = kx.is_induced_matching(cycle)
            is_acy, t_acy         = kx.is_acyclic_matching(matching)
        else:
            is_ind, t_ind, is_acy, t_acy = True, 0.0, True, 0.0
            
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

    return jsonify({'success': True, 'dataset_id': dataset_id})


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


@app.route('/api/run/greedy')
def run_greedy():
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})
    from kidney_exchange import FormulationComparer
    comparer = FormulationComparer(_cache['kx'])
    max_cands = request.args.get('max_candidates', default=500, type=int)
    return jsonify(comparer.run_greedy(max_candidates=min(max(max_cands, 25), 2000)))

@app.route('/api/run/pskcp')
def run_pskcp_formulation():
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})
    from kidney_exchange import FormulationComparer
    comparer = FormulationComparer(_cache['kx'])
    max_cands = request.args.get('max_candidates', default=500, type=int)
    return jsonify(comparer.run_pskcp(max_candidates=min(max(max_cands, 25), 2000)))

@app.route('/api/run/ilp-cf')
def run_ilp_cf():
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})
    from kidney_exchange import FormulationComparer
    comparer = FormulationComparer(_cache['kx'])
    max_cands = request.args.get('max_candidates', default=500, type=int)
    return jsonify(comparer.run_ilp_cf(max_candidates=min(max(max_cands, 25), 2000)))

@app.route('/api/run/ilp-ef')
def run_ilp_ef():
    if _cache['kx'] is None:
        return jsonify({'error': 'Load graph first via /api/load'})
    from kidney_exchange import FormulationComparer
    comparer = FormulationComparer(_cache['kx'])
    return jsonify(comparer.run_ilp_ef())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
