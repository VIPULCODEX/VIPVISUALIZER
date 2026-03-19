# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

from flask import Flask, jsonify, render_template
import os
from kidney_exchange import KidneyExchange

app = Flask(__name__)

# Cache results
cached_graph_data = None
cached_cycles_data = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/load')
def load_data():
    global cached_graph_data, cached_cycles_data
    
    # Get the number of nodes requested from the query parameters, defaulting to 50
    from flask import request
    num_nodes = request.args.get('nodes', default=50, type=int)
    
    csv_path = os.path.join(os.path.dirname(__file__), 'Kidney_Organ_SupplyChain_RawDataset.csv')
    
    kx = KidneyExchange()
    success = kx.load_from_csv(csv_path, max_rows=num_nodes)
    
    if not success:
        return jsonify({"error": "Failed to load CSV"})
        
    kx.build_graph()
    
    # Build graph payload
    nodes = [{"id": k, "label": f"{k} ({v['donor']}->{v['recipient']})", "donor_bg": v['donor'], "recipient_bg": v['recipient']} for k, v in kx.nodes.items()]
    edges = []
    for u, neighbors in kx.adj_list.items():
        for v in neighbors:
            edges.append({"from": u, "to": v})
            
    cached_graph_data = {"nodes": nodes, "edges": edges}
    
    # Pre-calculate cycles
    cycles = kx.find_cycles(max_length=3)
    
    cycle_results = []
    total_induced_time = 0
    total_acyclic_time = 0
    
    for cycle in cycles:
        matching = kx.extract_matching(cycle)
        is_induced, time_induced = kx.is_induced_matching(cycle)
        is_acyclic, time_acyclic = kx.is_acyclic_matching(matching)
        
        total_induced_time += time_induced
        total_acyclic_time += time_acyclic
        
        cycle_results.append({
            "cycle": cycle,
            "matching": matching,
            "is_induced": is_induced,
            "time_induced_ms": time_induced * 1000,
            "is_acyclic": is_acyclic,
            "time_acyclic_ms": time_acyclic * 1000
        })
        
    cached_cycles_data = {
        "cycles": cycle_results,
        "total_induced_time_ms": total_induced_time * 1000,
        "total_acyclic_time_ms": total_acyclic_time * 1000,
        "count": len(cycles)
    }
    
    return jsonify({"success": True})

@app.route('/api/graph')
def get_graph():
    return jsonify(cached_graph_data if cached_graph_data else {"nodes": [], "edges": []})

@app.route('/api/cycles')
def get_cycles():
    return jsonify(cached_cycles_data if cached_cycles_data else {"cycles": []})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
