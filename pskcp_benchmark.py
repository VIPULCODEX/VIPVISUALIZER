"""
Benchmark PS-KCP vs Greedy across various kidney exchange instance sizes.
Evaluates: transplant count, weight, runtime, kernel reduction, stability violations.
"""
import sys
import os
import time
import json

sys.path.insert(0, os.path.dirname(__file__))
from kidney_exchange import KidneyExchange, PSKCPSolver, MIAMSolver

CSV_PATH = os.path.join(os.path.dirname(__file__), 'Kidney_Organ_SupplyChain_RawDataset.csv')

# Test on various instance sizes
INSTANCE_SIZES = [10, 15, 20, 21, 25, 30, 40, 50, 60, 75, 100]

results = []

for n in INSTANCE_SIZES:
    print(f"\n{'='*60}")
    print(f"  INSTANCE SIZE: {n} donor-recipient pairs")
    print(f"{'='*60}")
    
    kx = KidneyExchange()
    if not kx.load_from_csv(CSV_PATH, max_rows=n):
        print(f"  FAILED to load {n} pairs")
        continue
    
    kx.build_graph()
    
    # Graph stats
    total_edges = sum(len(v) for v in kx.adj_list.values())
    cycles_found = kx.find_cycles(max_length=3)
    num_cycles = len(cycles_found)
    
    print(f"  Nodes: {len(kx.nodes)}")
    print(f"  Directed edges: {total_edges}")
    print(f"  Detected 2/3-cycles: {num_cycles}")
    
    # Run PS-KCP
    solver = PSKCPSolver(kx)
    t0 = time.perf_counter()
    try:
        pskcp_result = solver.run(
            max_length=3,
            max_candidates=500,
            num_hospitals=6,
            top_per_patient=12
        )
    except Exception as e:
        print(f"  PS-KCP FAILED: {e}")
        continue
    total_time = (time.perf_counter() - t0) * 1000
    
    greedy = pskcp_result['greedy']
    fpt = pskcp_result['fpt']
    
    row = {
        'n': n,
        'edges': total_edges,
        'detected_cycles': num_cycles,
        'candidate_count': pskcp_result['candidate_count'],
        'kernel_size': fpt.get('kernel_size', '?'),
        'kernel_reduction_pct': fpt.get('kernel_reduction', 0),
        'greedy_transplants': greedy['transplants'],
        'greedy_weight': greedy['weight'],
        'greedy_time_ms': greedy['time_ms'],
        'greedy_stability_violations': greedy['stability_violations'],
        'pskcp_transplants': fpt['transplants'],
        'pskcp_weight': fpt['weight'],
        'pskcp_time_ms': fpt['time_ms'],
        'pskcp_stability_violations': fpt['stability_violations'],
        'transplant_improvement': pskcp_result['transplant_improvement'],
        'weight_improvement': pskcp_result['weight_improvement'],
        'stability_improvement': pskcp_result['stability_improvement'],
        'total_time_ms': round(total_time, 2),
        'used_greedy_fallback': fpt.get('used_greedy_fallback', False),
    }
    results.append(row)
    
    print(f"\n  --- Greedy ---")
    print(f"  Transplants: {greedy['transplants']}, Weight: {greedy['weight']}, Time: {greedy['time_ms']} ms")
    print(f"  Stability violations: {greedy['stability_violations']}")
    
    print(f"\n  --- PS-KCP (FPT) ---")
    print(f"  Transplants: {fpt['transplants']}, Weight: {fpt['weight']}, Time: {fpt['time_ms']} ms")
    print(f"  Stability violations: {fpt['stability_violations']}")
    print(f"  Kernel reduction: {fpt.get('kernel_reduction', 0)}%")
    print(f"  Used greedy fallback: {fpt.get('used_greedy_fallback', False)}")
    
    if pskcp_result['transplant_improvement'] > 0:
        print(f"\n  [WIN] PS-KCP found {pskcp_result['transplant_improvement']} MORE transplants than Greedy!")
    elif pskcp_result['transplant_improvement'] == 0:
        print(f"\n  [TIE] PS-KCP and Greedy found the SAME number of transplants.")
    else:
        print(f"\n  [LOSS] Greedy found more transplants (unusual).")


# ── Summary table ────────────────────────────────────────────
print(f"\n\n{'='*120}")
print(f"  SUMMARY TABLE")
print(f"{'='*120}")
header = f"{'N':>4} | {'Edges':>6} | {'Cycles':>6} | {'Cands':>5} | {'Kern':>5} | {'KR%':>5} | {'G_Tx':>4} | {'P_Tx':>4} | {'Diff':>4} | {'G_Wt':>8} | {'P_Wt':>8} | {'G_ms':>8} | {'P_ms':>10} | {'G_SV':>4} | {'P_SV':>4} | {'Fallback':>8}"
print(header)
print("-" * 120)

for r in results:
    line = (
        f"{r['n']:>4} | {r['edges']:>6} | {r['detected_cycles']:>6} | "
        f"{r['candidate_count']:>5} | {r['kernel_size']:>5} | {r['kernel_reduction_pct']:>5.1f} | "
        f"{r['greedy_transplants']:>4} | {r['pskcp_transplants']:>4} | {r['transplant_improvement']:>4} | "
        f"{r['greedy_weight']:>8.1f} | {r['pskcp_weight']:>8.1f} | "
        f"{r['greedy_time_ms']:>8.3f} | {r['pskcp_time_ms']:>10.3f} | "
        f"{r['greedy_stability_violations']:>4} | {r['pskcp_stability_violations']:>4} | "
        f"{'YES' if r['used_greedy_fallback'] else 'NO':>8}"
    )
    print(line)

# Count where PS-KCP strictly beats greedy
wins = sum(1 for r in results if r['transplant_improvement'] > 0)
ties = sum(1 for r in results if r['transplant_improvement'] == 0)
losses = sum(1 for r in results if r['transplant_improvement'] < 0)

print(f"\n  PS-KCP wins: {wins}/{len(results)}, Ties: {ties}/{len(results)}, Losses: {losses}/{len(results)}")
print(f"  Average kernel reduction: {sum(r['kernel_reduction_pct'] for r in results)/len(results):.1f}%")
print(f"  Average transplant improvement: {sum(r['transplant_improvement'] for r in results)/len(results):.1f}")
print(f"  Average weight improvement: {sum(r['weight_improvement'] for r in results)/len(results):.1f}")

# Save JSON for further analysis
with open(os.path.join(os.path.dirname(__file__), 'pskcp_benchmark_results.json'), 'w') as f:
    json.dump(results, f, indent=2)
print(f"\n  Results saved to pskcp_benchmark_results.json")
