# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

import pandas as pd
import time
import random
import hashlib


# ─────────────────────────────────────────────────────────────
#  Blood-type donation compatibility rules
# ─────────────────────────────────────────────────────────────
_DONATE_RULES = {
    'O':  ['O', 'A', 'B', 'AB'],
    'A':  ['A', 'AB'],
    'B':  ['B', 'AB'],
    'AB': ['AB'],
}


class KidneyExchange:
    """Compatibility graph builder and basic cycle analyser."""

    def __init__(self):
        self.nodes    = {}   # pair_id -> {'donor': bg, 'recipient': bg}
        self.adj_list = {}   # directed compatibility edges

    def add_pair(self, pair_id, donor_bg, recipient_bg):
        self.nodes[pair_id] = {'donor': donor_bg, 'recipient': recipient_bg}

    def load_from_csv(self, file_path, max_rows=None):
        try:
            df = pd.read_csv(file_path)
            if max_rows:
                df = df.head(max_rows)
            for _, row in df.iterrows():
                self.add_pair(
                    str(row['Patient_ID']).strip(),
                    str(row['Donor_BloodType']).strip().upper(),
                    str(row['Patient_BloodType']).strip().upper(),
                )
            print(f"Loaded {len(self.nodes)} pairs from {file_path}")
            return True
        except Exception as e:
            print(f"CSV load error: {e}")
            return False

    def can_donate(self, donor, recipient):
        return recipient in _DONATE_RULES.get(donor, [])

    def build_graph(self):
        self.adj_list = {u: [] for u in self.nodes}
        for u, ud in self.nodes.items():
            for v, vd in self.nodes.items():
                if u != v and self.can_donate(ud['donor'], vd['recipient']):
                    self.adj_list[u].append(v)

    # ── Cycle detection ──────────────────────────────────────
    def find_cycles(self, max_length=3):
        cycles = []

        def dfs(start, cur, path):
            if len(path) > max_length:
                return
            for nb in self.adj_list.get(cur, []):
                if nb == start and 2 <= len(path) <= max_length:
                    cycles.append(path[:])
                elif nb not in path:
                    dfs(start, nb, path + [nb])

        for node in self.nodes:
            dfs(node, node, [node])

        seen, unique = set(), []
        for c in cycles:
            mi  = c.index(min(c))
            key = tuple(c[mi:] + c[:mi])
            if key not in seen:
                seen.add(key)
                unique.append(list(key))
        return unique

    def extract_matching(self, cycle):
        return [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]

    # ── Induced matching check ───────────────────────────────
    def is_induced_matching(self, cycle):
        matching     = set(self.extract_matching(cycle))
        cycle_nodes  = set(cycle)
        start_t      = time.perf_counter()
        for _ in range(100):
            ok = True
            for u in cycle_nodes:
                for v in self.adj_list.get(u, []):
                    if v in cycle_nodes and (u, v) not in matching:
                        ok = False
                        break
                if not ok:
                    break
        return ok, time.perf_counter() - start_t

    # ── Acyclic matching check (iterative DFS) ───────────────
    def is_acyclic_matching(self, matching):
        adj = {}
        for u, v in matching:
            adj.setdefault(u, []).append(v)
            adj.setdefault(v, [])

        start_t = time.perf_counter()
        for _ in range(100):
            visited, in_stack, ok = set(), set(), True

            def _has_cycle(start):
                stack = [(start, iter(adj.get(start, [])))]
                in_stack.add(start)
                visited.add(start)
                while stack:
                    node, children = stack[-1]
                    try:
                        child = next(children)
                        if child in in_stack:
                            return True
                        if child not in visited:
                            visited.add(child)
                            in_stack.add(child)
                            stack.append((child, iter(adj.get(child, []))))
                    except StopIteration:
                        in_stack.discard(node)
                        stack.pop()
                return False

            for node in adj:
                if node not in visited:
                    if _has_cycle(node):
                        ok = False
                        break
        return ok, time.perf_counter() - start_t


# ─────────────────────────────────────────────────────────────
#  MIAM Solver
#  Mixed Induced-Acyclic Matching on Kidney Exchange Graphs
#
#  Model (from project research):
#    Compatibility graph G = (V, E)  — blood-type compatibility
#    Conflict      graph C = (V, F)  — shared hospital/crossmatch resource
#
#  MIAM = maximum-weight set S of donor-recipient pairs such that:
#    (1) S is an independent set in G  (no direct competition between pairs)
#    (2) S is an independent set in C  (no resource conflict)
#    (3) Induced matching constraint holds for the exchange edges
#
#  Algorithm:
#    Step 1 — Build conflict graph C (hospital-resource simulation)
#    Step 2 — Assign weights (blood-type rarity + urgency)
#    Step 3 — Kernelise with 3 reduction rules  →  kernel size O(k)
#    Step 4 — Bounded search tree on kernel     →  O(2^k · n)
#    Step 5 — Compare with greedy baseline
# ─────────────────────────────────────────────────────────────

# Weight for each (donor_bg, recipient_bg) pair
_PAIR_WEIGHT = {
    ('O',  'O'):  2, ('O',  'A'):  4, ('O',  'B'):  4, ('O',  'AB'): 6,
    ('A',  'A'):  2, ('A',  'AB'): 3,
    ('B',  'B'):  2, ('B',  'AB'): 3,
    ('AB', 'AB'): 1,
}


class MIAMSolver:
    """
    Implements the FPT MIAM algorithm as described in the project research plan.
    """

    def __init__(self, kx: KidneyExchange):
        self.kx              = kx
        self.conflict_adj    = {}   # v -> set of conflict neighbours
        self.weights         = {}   # v -> int weight
        self.conflict_edges  = []   # list of (u,v) for frontend rendering
        self.n_conflict      = 0

    def _stable_bucket(self, value: str, modulo: int) -> int:
        """Return a deterministic bucket for repeatable local and Render runs."""
        digest = hashlib.sha256(str(value).encode('utf-8')).hexdigest()
        return int(digest[:12], 16) % modulo

    def _compat_neighbours(self, v: str, active=None) -> set:
        """Compatibility neighbours in either direction of the directed graph."""
        neighbours = set(self.kx.adj_list.get(v, []))
        for u, out_neighbours in self.kx.adj_list.items():
            if v in out_neighbours:
                neighbours.add(u)
        if active is not None:
            neighbours &= active
        return neighbours

    # ── Step 1: Assign weights ───────────────────────────────
    def assign_weights(self):
        """
        w(v) = blood-type rarity score  +  urgency proxy (from patient ID hash).
        Higher weight = more valuable pair to include in the MIAM.
        """
        for pid, d in self.kx.nodes.items():
            base    = _PAIR_WEIGHT.get((d['donor'], d['recipient']), 1)
            urgency = self._stable_bucket(pid, 3) + 1   # 1, 2, or 3
            self.weights[pid] = base + urgency

    # ── Step 2: Build conflict graph C ───────────────────────
    def build_conflict_graph(self, num_hospitals: int = 6, seed: int = 42):
        """
        Simulate hospital/crossmatch resource conflicts.

        Two pairs (u, v) conflict when:
          - They are assigned to the same hospital (hash-based simulation)
          - AND they share the same donor blood type
            (same crossmatch reagent pool  →  lab resource conflict)

        This is biologically motivated: a crossmatch lab handling
        the same blood type can only process one pair at a time.
        """
        random.seed(seed)
        nodes = list(self.kx.nodes.keys())

        # Assign each patient pair to a hospital
        hospital = {p: self._stable_bucket(p, num_hospitals) for p in nodes}

        self.conflict_adj   = {p: set() for p in nodes}
        self.conflict_edges = []
        self.n_conflict     = 0

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                u, v = nodes[i], nodes[j]
                if (hospital[u] == hospital[v] and
                        self.kx.nodes[u]['donor'] == self.kx.nodes[v]['donor']):
                    self.conflict_adj[u].add(v)
                    self.conflict_adj[v].add(u)
                    self.conflict_edges.append({'from': u, 'to': v})
                    self.n_conflict += 1

        return self.n_conflict

    # ── Step 3: Weighted kernelisation ───────────────────────
    def kernelise(self, active: set):
        """
        Apply three reduction rules repeatedly until no rule fires.

        Rule 1 — Isolated vertex removal:
            If v has no neighbours in G[active] AND no neighbours in C[active],
            it cannot contribute to any exchange → remove it.

        Rule 2 — Forced inclusion:
            If v has no conflict neighbours in C[active], it never violates
            the conflict constraint → force-include v, then remove v's
            G-neighbours (induced constraint: no direct competitors).

        Rule 3 — Dominated vertex:
            If w(u) ≤ w(v) AND N_G(u) ⊆ N_G(v) AND N_C(u) ⊆ N_C(v),
            then u is dominated by v → remove u (never in an optimal solution).

        Returns: (kernel, forced_in, forced_out)
        """
        active     = set(active)
        forced_in  = set()
        forced_out = set()
        changed    = True

        while changed:
            changed    = False
            to_remove  = set()

            for v in list(active):
                if v in to_remove:
                    continue
                gN = self._compat_neighbours(v, active)
                cN = self.conflict_adj.get(v, set())  & active

                # Rule 1
                if not gN and not cN:
                    to_remove.add(v)
                    changed = True
                    continue

                # Rule 2
                if not cN:
                    forced_in.add(v)
                    to_remove.add(v)
                    for nb in gN:         # induced constraint: remove G-neighbours
                        forced_out.add(nb)
                        to_remove.add(nb)
                    changed = True

            active -= to_remove

        # Rule 3: single pass dominated-vertex removal
        lst = list(active)
        dominated = set()
        for i, u in enumerate(lst):
            if u in dominated:
                continue
            gNu = self._compat_neighbours(u, active)
            cNu = self.conflict_adj.get(u, set())  & active
            for j, v in enumerate(lst):
                if i == j or v in dominated:
                    continue
                if self.weights.get(u, 1) <= self.weights.get(v, 1):
                    gNv = self._compat_neighbours(v, active)
                    cNv = self.conflict_adj.get(v, set())  & active
                    if gNu <= gNv and cNu <= cNv:
                        dominated.add(u)
                        break

        active     -= dominated
        forced_out |= dominated

        return active, forced_in, forced_out

    # ── Helper: valid addition check ─────────────────────────
    def _can_add(self, v, miam_set: set) -> bool:
        """
        Check if adding v to miam_set keeps the set valid:
          - No conflict edge to any member of miam_set
          - No G-edge in either direction to any member of miam_set
        """
        cN = self.conflict_adj.get(v, set())
        gN = self._compat_neighbours(v)
        return not (cN & miam_set) and not (gN & miam_set)

    # ── Step 4a: Greedy MIAM ─────────────────────────────────
    def solve_greedy(self):
        """
        Greedy baseline — O(n²).
        Sort by weight (desc), greedily include each vertex if valid.
        """
        start = time.perf_counter()
        order = sorted(self.kx.nodes, key=lambda v: self.weights.get(v, 1), reverse=True)

        miam, excluded = [], set()
        for v in order:
            if v in excluded:
                continue
            if self._can_add(v, set(miam)):
                miam.append(v)
                for nb in self._compat_neighbours(v):
                    excluded.add(nb)

        elapsed = (time.perf_counter() - start) * 1000
        return {
            'solution': miam,
            'size':     len(miam),
            'weight':   sum(self.weights.get(v, 1) for v in miam),
            'time_ms':  round(elapsed, 4),
        }

    # ── Step 4b: FPT MIAM (kernelise + bounded search tree) ──
    def solve_fpt(self, max_k: int = 12):
        """
        FPT Algorithm — O(2^k · n) after kernelisation.

        After kernelisation, run a bounded search tree:
          Pick the highest-weight vertex v in the kernel.
          Branch A: include v → remove v, its G-neighbours, its C-neighbours.
          Branch B: exclude v → remove v.
          Recurse until k exhausted or kernel empty.

        Return the best (highest-weight) solution found.
        """
        start = time.perf_counter()

        active = set(self.kx.nodes.keys())
        kernel, forced_in, forced_out = self.kernelise(active)
        kernel_size   = len(kernel)
        original_size = len(self.kx.nodes)

        best = {'w': sum(self.weights.get(v, 1) for v in forced_in),
                'sol': list(forced_in)}

        def _search(remaining: set, current: set, cur_w: int, depth: int):
            if not remaining or depth > max_k:
                if cur_w > best['w']:
                    best['w']   = cur_w
                    best['sol'] = list(current)
                return

            # Pick highest-weight candidate
            v   = max(remaining, key=lambda x: self.weights.get(x, 1))
            w_v = self.weights.get(v, 1)

            # Branch A — include v (valid addition check)
            if self._can_add(v, current):
                blocked = (
                    self._compat_neighbours(v) |          # G-neighbours (induced)
                    self.conflict_adj.get(v, set())        # C-neighbours (conflict)
                ) & remaining
                _search(
                    remaining - {v} - blocked,
                    current | {v},
                    cur_w + w_v,
                    depth + 1,
                )

            # Branch B — exclude v
            _search(remaining - {v}, current, cur_w, depth + 1)

        _search(kernel, set(forced_in), best['w'], 0)

        elapsed = (time.perf_counter() - start) * 1000
        reduction_pct = round((1 - kernel_size / max(original_size, 1)) * 100, 1)

        return {
            'solution':         best['sol'],
            'size':             len(best['sol']),
            'weight':           best['w'],
            'kernel_size':      kernel_size,
            'original_size':    original_size,
            'kernel_reduction': reduction_pct,
            'forced_in':        len(forced_in),
            'forced_out':       len(forced_out),
            'time_ms':          round(elapsed, 4),
        }

    # ── Full benchmark ───────────────────────────────────────
    def run(self, num_hospitals: int = 6):
        """Build conflict graph, assign weights, run both algorithms."""
        self.assign_weights()
        self.build_conflict_graph(num_hospitals=num_hospitals)

        greedy = self.solve_greedy()
        fpt    = self.solve_fpt()

        return {
            'conflict_edges':       self.conflict_edges,
            'n_conflict_edges':     self.n_conflict,
            'greedy':               greedy,
            'fpt':                  fpt,
            'weight_improvement':   round(fpt['weight'] - greedy['weight'], 2),
            'size_improvement':     fpt['size'] - greedy['size'],
        }
