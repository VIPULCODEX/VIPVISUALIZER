"""
Deep PS-KCP evaluation informed by Barkel et al. (EJOR 2026) survey.
Tests:
1. PS-KCP vs ILP (using PuLP/scipy) on the same kernelized instances
2. Impact of candidate cap on solution quality
3. Scalability analysis with timing breakdown
4. Gap analysis: how far is PS-KCP from optimal?
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(__file__))
from kidney_exchange import KidneyExchange, PSKCPSolver

CSV_PATH = os.path.join(os.path.dirname(__file__), 'Kidney_Organ_SupplyChain_RawDataset.csv')

# Try to import PuLP for ILP comparison
try:
    from scipy.optimize import linprog, milp, LinearConstraint, Bounds
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

print("=" * 70)
print("  DEEP PS-KCP EVALUATION (Informed by Barkel et al. EJOR 2026)")
print("=" * 70)
print(f"  scipy available for ILP: {HAS_SCIPY}")

# ============================================================
# TEST 1: Impact of candidate cap on solution quality
# ============================================================
print("\n\n" + "=" * 70)
print("  TEST 1: IMPACT OF CANDIDATE CAP ON SOLUTION QUALITY")
print("  (Key weakness: PS-KCP truncates cycle enumeration)")
print("=" * 70)

N = 30  # Fixed instance size
kx = KidneyExchange()
kx.load_from_csv(CSV_PATH, max_rows=N)
kx.build_graph()
all_cycles = kx.find_cycles(max_length=3)
print(f"\n  Instance: N={N}, Total real cycles: {len(all_cycles)}")

for cap in [50, 100, 200, 350, 500, 702]:
    solver = PSKCPSolver(kx)
    result = solver.run(max_length=3, max_candidates=cap, num_hospitals=6, top_per_patient=12)
    fpt = result['fpt']
    greedy = result['greedy']
    actual_cands = result['candidate_count']
    print(f"  Cap={cap:>4} | Actual candidates={actual_cands:>4} | "
          f"Greedy: {greedy['transplants']:>2} tx ({greedy['weight']:>7.1f} wt) | "
          f"PS-KCP: {fpt['transplants']:>2} tx ({fpt['weight']:>7.1f} wt) | "
          f"Kernel: {fpt.get('kernel_size', '?'):>4} | "
          f"Time: {fpt['time_ms']:>8.1f} ms")


# ============================================================
# TEST 2: Timing breakdown - where does PS-KCP spend time?
# ============================================================
print("\n\n" + "=" * 70)
print("  TEST 2: TIMING BREAKDOWN (Where PS-KCP spends time)")
print("=" * 70)

for N in [15, 25, 50, 75]:
    kx = KidneyExchange()
    kx.load_from_csv(CSV_PATH, max_rows=N)
    kx.build_graph()
    
    solver = PSKCPSolver(kx)
    
    t0 = time.perf_counter()
    solver.build_candidates(max_length=3, max_candidates=500)
    t_enum = (time.perf_counter() - t0) * 1000
    
    t0 = time.perf_counter()
    solver.build_conflict_graph(num_hospitals=6)
    t_conflict = (time.perf_counter() - t0) * 1000
    
    t0 = time.perf_counter()
    greedy = solver.solve_greedy()
    t_greedy = (time.perf_counter() - t0) * 1000
    
    t0 = time.perf_counter()
    fpt = solver.solve_fpt(top_per_patient=12)
    t_fpt = (time.perf_counter() - t0) * 1000
    
    total = t_enum + t_conflict + t_greedy + t_fpt
    
    print(f"\n  N={N:>3}: Total={total:>8.1f} ms")
    print(f"    Cycle enumeration:  {t_enum:>8.1f} ms ({t_enum/total*100:>5.1f}%)")
    print(f"    Conflict graph:     {t_conflict:>8.1f} ms ({t_conflict/total*100:>5.1f}%)")
    print(f"    Greedy solve:       {t_greedy:>8.1f} ms ({t_greedy/total*100:>5.1f}%)")
    print(f"    FPT branch+bound:   {t_fpt:>8.1f} ms ({t_fpt/total*100:>5.1f}%)")
    print(f"    Candidates: {len(solver.candidates)}, Kernel: {fpt.get('kernel_size', '?')}")


# ============================================================
# TEST 3: ILP on kernel vs Branch-and-Bound on kernel
# (This is the key test: does replacing B&B with ILP help?)
# ============================================================
print("\n\n" + "=" * 70)
print("  TEST 3: ILP vs BRANCH-AND-BOUND ON KERNELIZED INSTANCES")
print("  (Can we improve PS-KCP by swapping the solver?)")
print("=" * 70)

if HAS_SCIPY:
    import numpy as np
    
    for N in [15, 20, 21, 25, 30, 50, 75]:
        kx = KidneyExchange()
        kx.load_from_csv(CSV_PATH, max_rows=N)
        kx.build_graph()
        
        solver = PSKCPSolver(kx)
        solver.build_candidates(max_length=3, max_candidates=500)
        solver.build_conflict_graph(num_hospitals=6)
        
        # Get kernel
        kernel, forced, removed = solver.kernelise(top_per_patient=12)
        kernel_ids = sorted(kernel)
        forced_ids = sorted(forced)
        
        # Forced weight
        forced_weight = sum(solver.candidates[cid].weight for cid in forced_ids)
        forced_transplants = sum(solver.candidates[cid].transplant_count for cid in forced_ids)
        
        if len(kernel_ids) == 0:
            print(f"\n  N={N:>3}: Kernel empty, forced={len(forced_ids)}, "
                  f"transplants={forced_transplants}, weight={forced_weight:.1f}")
            continue
        
        # Build ILP: maximize sum(w_i * x_i) subject to x_i + x_j <= 1 for conflicts
        n_vars = len(kernel_ids)
        id_to_idx = {cid: i for i, cid in enumerate(kernel_ids)}
        
        # Objective: maximize weight (scipy minimizes, so negate)
        weights = np.array([solver.candidates[cid].weight for cid in kernel_ids])
        c = -weights  # negate for minimization
        
        # Constraints: x_i + x_j <= 1 for each conflict pair
        conflict_pairs = []
        for i, cid_a in enumerate(kernel_ids):
            for cid_b in solver.conflict_adj.get(cid_a, set()):
                if cid_b in id_to_idx:
                    j = id_to_idx[cid_b]
                    if i < j:  # avoid duplicates
                        conflict_pairs.append((i, j))
        
        if conflict_pairs:
            A_ub = np.zeros((len(conflict_pairs), n_vars))
            b_ub = np.ones(len(conflict_pairs))
            for row, (i, j) in enumerate(conflict_pairs):
                A_ub[row, i] = 1
                A_ub[row, j] = 1
        else:
            A_ub = None
            b_ub = None
        
        # Solve ILP
        t0 = time.perf_counter()
        try:
            integrality = np.ones(n_vars)  # all binary
            bounds_obj = Bounds(lb=0, ub=1)
            
            if A_ub is not None:
                constraints = LinearConstraint(A_ub, ub=b_ub)
                result_ilp = milp(c, integrality=integrality, bounds=bounds_obj, constraints=constraints)
            else:
                result_ilp = milp(c, integrality=integrality, bounds=bounds_obj)
            
            t_ilp = (time.perf_counter() - t0) * 1000
            
            if result_ilp.success:
                ilp_selected = [kernel_ids[i] for i in range(n_vars) if result_ilp.x[i] > 0.5]
                ilp_weight = forced_weight + sum(solver.candidates[cid].weight for cid in ilp_selected)
                ilp_transplants = forced_transplants + sum(solver.candidates[cid].transplant_count for cid in ilp_selected)
            else:
                ilp_weight = forced_weight
                ilp_transplants = forced_transplants
                ilp_selected = []
        except Exception as e:
            t_ilp = (time.perf_counter() - t0) * 1000
            print(f"\n  N={N}: ILP failed: {e}")
            continue
        
        # Compare with PS-KCP's B&B
        t0 = time.perf_counter()
        fpt = solver.solve_fpt(top_per_patient=12)
        t_bb = (time.perf_counter() - t0) * 1000
        
        greedy = solver.solve_greedy()
        
        print(f"\n  N={N:>3} | Kernel: {n_vars:>3} candidates | Conflicts: {len(conflict_pairs):>4} pairs")
        print(f"    Greedy:   {greedy['transplants']:>2} tx, wt={greedy['weight']:>7.1f}, time={greedy['time_ms']:>8.3f} ms")
        print(f"    PS-KCP:   {fpt['transplants']:>2} tx, wt={fpt['weight']:>7.1f}, time={t_bb:>8.3f} ms")
        print(f"    ILP:      {ilp_transplants:>2} tx, wt={ilp_weight:>7.1f}, time={t_ilp:>8.3f} ms")
        
        if ilp_transplants > fpt['transplants']:
            print(f"    >>> ILP BEATS PS-KCP by {ilp_transplants - fpt['transplants']} transplants!")
        elif ilp_transplants == fpt['transplants']:
            if abs(ilp_weight - fpt['weight']) > 0.1:
                print(f"    >>> Same transplants, ILP weight diff: {ilp_weight - fpt['weight']:+.1f}")
            else:
                print(f"    >>> ILP and PS-KCP agree (same transplants and weight)")
        else:
            print(f"    >>> PS-KCP beats ILP (unusual - check constraints)")

else:
    print("  scipy not available - skipping ILP comparison")
    print("  Install with: pip install scipy")


# ============================================================
# TEST 4: Chain support analysis
# ============================================================
print("\n\n" + "=" * 70)
print("  TEST 4: WHAT PS-KCP IS MISSING (Per Barkel et al. survey)")
print("=" * 70)

print("""
  According to the EJOR 2026 survey, the state-of-the-art methods include:

  FEATURES PS-KCP IS MISSING:
  ----------------------------
  1. CHAINS: PS-KCP only handles cycles (2-way, 3-way).
     Real KEPs use altruistic donor chains that can be 3-10+ transplants long.
     The survey shows chains can increase transplants by 20-40%.

  2. ILP MODELS: The survey benchmarks these key formulations:
     - CF  (Cycle Formulation)      - exponential variables, strong bounds
     - EF  (Edge Formulation)       - polynomial variables, weaker bounds
     - EEF (Extended Edge Form.)    - polynomial, stronger than EF
     - PICEF (Position-Indexed)     - best overall performer in survey
     - HPIEF (Hybrid PICEF+EEF)     - strong on some instances
     PS-KCP uses NONE of these. It uses greedy + branch-and-bound.

  3. HIERARCHICAL OPTIMIZATION:
     Real KEPs (UK, Spain, Netherlands) optimize multiple objectives:
     - Max transplants -> Max exchanges -> Max back-arcs -> Max weight
     PS-KCP uses a single weighted objective only.

  4. UNCERTAINTY/ROBUSTNESS:
     Real KEPs account for transplant failure (69% proceed in UK).
     PS-KCP assumes all selected transplants succeed.

  5. SCALE:
     Survey tests instances up to 1000+ pairs with 5% NDDs.
     PS-KCP caps at 500 candidates (not pairs - candidate CYCLES).
     At N=100 pairs there are 30,546 cycles but only 500 evaluated.

  WHAT PS-KCP DOES DIFFERENTLY (potential novelty):
  ---------------------------------------------------
  1. KERNELIZATION as preprocessing before optimization.
     The survey does NOT prominently feature kernelization.
     This is PS-KCP's unique contribution if formalized properly.

  2. PREFERENCE-STABILITY proxy scoring.
     The survey covers preferences (Section 2.7) but most methods
     don't integrate stability into the cycle packing objective.

  3. CONFLICT GRAPH over cycles (not just vertex-disjointness).
     The survey's ILP models handle disjointness via constraints,
     PS-KCP explicitly models it as a graph. Different perspective.
""")


# ============================================================
# TEST 5: Gap from cycle formulation optimal (estimate)
# ============================================================
print("=" * 70)
print("  TEST 5: OPTIMALITY GAP ESTIMATE")
print("  (Upper bound from LP relaxation vs PS-KCP solution)")
print("=" * 70)

if HAS_SCIPY:
    for N in [21, 30, 50]:
        kx = KidneyExchange()
        kx.load_from_csv(CSV_PATH, max_rows=N)
        kx.build_graph()
        
        solver = PSKCPSolver(kx)
        solver.build_candidates(max_length=3, max_candidates=500)
        solver.build_conflict_graph(num_hospitals=6)
        
        # Full ILP (no kernelization) for ground truth
        all_ids = sorted(solver.candidates.keys())
        n_vars = len(all_ids)
        id_to_idx = {cid: i for i, cid in enumerate(all_ids)}
        
        weights = np.array([solver.candidates[cid].weight for cid in all_ids])
        c = -weights
        
        conflict_pairs = []
        for i, cid_a in enumerate(all_ids):
            for cid_b in solver.conflict_adj.get(cid_a, set()):
                if cid_b in id_to_idx:
                    j = id_to_idx[cid_b]
                    if i < j:
                        conflict_pairs.append((i, j))
        
        if conflict_pairs:
            A_ub = np.zeros((len(conflict_pairs), n_vars))
            b_ub = np.ones(len(conflict_pairs))
            for row, (i, j) in enumerate(conflict_pairs):
                A_ub[row, i] = 1
                A_ub[row, j] = 1
        
        # LP relaxation (upper bound)
        t0 = time.perf_counter()
        if conflict_pairs:
            lp_result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=[(0, 1)] * n_vars)
        else:
            lp_result = linprog(c, bounds=[(0, 1)] * n_vars)
        t_lp = (time.perf_counter() - t0) * 1000
        lp_upper_bound = -lp_result.fun if lp_result.success else float('inf')
        
        # Full ILP (optimal)
        t0 = time.perf_counter()
        integrality = np.ones(n_vars)
        bounds_obj = Bounds(lb=0, ub=1)
        if conflict_pairs:
            constraints = LinearConstraint(A_ub, ub=b_ub)
            ilp_result = milp(c, integrality=integrality, bounds=bounds_obj, constraints=constraints)
        else:
            ilp_result = milp(c, integrality=integrality, bounds=bounds_obj)
        t_ilp = (time.perf_counter() - t0) * 1000
        
        ilp_optimal = -ilp_result.fun if ilp_result.success else 0
        ilp_tx = sum(solver.candidates[all_ids[i]].transplant_count 
                     for i in range(n_vars) if ilp_result.x[i] > 0.5) if ilp_result.success else 0
        
        # PS-KCP result
        full_result = solver.run(max_length=3, max_candidates=500, num_hospitals=6, top_per_patient=12)
        pskcp_wt = full_result['fpt']['weight']
        pskcp_tx = full_result['fpt']['transplants']
        greedy_wt = full_result['greedy']['weight']
        greedy_tx = full_result['greedy']['transplants']
        
        gap_pskcp = ((ilp_optimal - pskcp_wt) / ilp_optimal * 100) if ilp_optimal > 0 else 0
        gap_greedy = ((ilp_optimal - greedy_wt) / ilp_optimal * 100) if ilp_optimal > 0 else 0
        
        print(f"\n  N={N:>3} | Candidates: {n_vars} | Conflicts: {len(conflict_pairs)}")
        print(f"    LP upper bound:     {lp_upper_bound:>8.1f} wt  ({t_lp:.1f} ms)")
        print(f"    ILP optimal:        {ilp_optimal:>8.1f} wt, {ilp_tx:>2} tx  ({t_ilp:.1f} ms)")
        print(f"    PS-KCP:             {pskcp_wt:>8.1f} wt, {pskcp_tx:>2} tx")
        print(f"    Greedy:             {greedy_wt:>8.1f} wt, {greedy_tx:>2} tx")
        print(f"    PS-KCP gap from optimal: {gap_pskcp:>5.1f}%")
        print(f"    Greedy gap from optimal: {gap_greedy:>5.1f}%")

print("\n\n  Done!")
