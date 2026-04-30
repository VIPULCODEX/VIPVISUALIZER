# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

import pandas as pd
import time
import random
import hashlib
from dataclasses import dataclass


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
                pair_id = str(row['Patient_ID']).strip()
                self.add_pair(
                    pair_id,
                    str(row['Donor_BloodType']).strip().upper(),
                    str(row['Patient_BloodType']).strip().upper(),
                )
                self.nodes[pair_id].update({
                    'patient_age': self._safe_float(row.get('Patient_Age'), 0),
                    'patient_weight': self._safe_float(row.get('Patient_Weight'), 0),
                    'patient_bmi': self._safe_float(row.get('Patient_BMI'), 0),
                    'diagnosis': str(row.get('Diagnosis_Result', '')).strip(),
                    'biological_markers': self._safe_float(row.get('Biological_Markers'), 0),
                    'organ_status': str(row.get('Organ_Status', '')).strip(),
                    'donor_id': str(row.get('Donor_ID', '')).strip(),
                    'donor_age': self._safe_float(row.get('Donor_Age'), 0),
                    'donor_weight': self._safe_float(row.get('Donor_Weight'), 0),
                    'donor_approved': str(row.get('Donor_Medical_Approval', '')).strip().lower() == 'yes',
                    'match_status': str(row.get('Match_Status', '')).strip(),
                    'organ_health': self._safe_float(row.get('RealTime_Organ_HealthScore'), 0),
                    'organ_alert': str(row.get('Organ_Condition_Alert', '')).strip(),
                    'survival': self._safe_float(row.get('Predicted_Survival_Chance'), 0),
                    'scan_time': str(row.get('Timestamp_Organ_Scanned', '')).strip(),
                })
            print(f"Loaded {len(self.nodes)} pairs from {file_path}")
            return True
        except Exception as e:
            print(f"CSV load error: {e}")
            return False

    def _safe_float(self, value, default=0):
        try:
            if pd.isna(value):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

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


@dataclass(frozen=True)
class CycleCandidate:
    """One executable kidney exchange cycle represented as a meta-node."""
    id: str
    nodes: tuple
    edges: tuple
    weight: float
    transplant_count: int
    preference_gain: float
    stability_margin: float


class PSKCPSolver:
    """
    Preference-Stable Kernelized Cycle Packing.

    The solver upgrades the prototype MIAM idea from selecting patient-pair
    vertices to selecting disjoint 2/3-cycle exchange candidates.
    """

    def __init__(self, kx: KidneyExchange):
        self.kx = kx
        self.candidates = {}
        self.conflict_adj = {}
        self.preference_cache = {}
        self.hospital_cache = {}

    def _stable_bucket(self, value: str, modulo: int) -> int:
        digest = hashlib.sha256(str(value).encode('utf-8')).hexdigest()
        return int(digest[:12], 16) % modulo

    def _diagnosis_urgency(self, diagnosis: str) -> float:
        text = diagnosis.lower()
        if 'esrd' in text or 'stage 5' in text:
            return 3.0
        if 'stage 4' in text:
            return 2.0
        if 'stage 3' in text:
            return 1.0
        return 0.5

    def _patient_priority(self, pair_id: str) -> float:
        node = self.kx.nodes[pair_id]
        survival = node.get('survival', 0) / 100
        health = node.get('organ_health', 0)
        urgency = self._diagnosis_urgency(node.get('diagnosis', ''))
        alert = 0.8 if node.get('organ_alert', '').lower() == 'critical' else 0.2
        return urgency + survival + health + alert

    def _preference_score(self, recipient_pair: str, donor_pair: str) -> float:
        key = (recipient_pair, donor_pair)
        if key in self.preference_cache:
            return self.preference_cache[key]

        recipient = self.kx.nodes[recipient_pair]
        donor = self.kx.nodes[donor_pair]
        donor_quality = donor.get('survival', 0) / 20
        organ_health = donor.get('organ_health', 0) * 2
        approval = 1.5 if donor.get('donor_approved') else -0.5
        age_fit = max(0, 1.5 - abs(donor.get('donor_age', 0) - 35) / 35)
        weight_fit = max(0, 1.0 - abs(donor.get('donor_weight', 0) - recipient.get('patient_weight', 0)) / 80)
        blood_bonus = _PAIR_WEIGHT.get((donor.get('donor'), recipient.get('recipient')), 1) / 2
        score = donor_quality + organ_health + approval + age_fit + weight_fit + blood_bonus
        self.preference_cache[key] = round(score, 4)
        return self.preference_cache[key]

    def _cycle_edges(self, cycle):
        return tuple((cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle)))

    def _canonical_cycle(self, cycle):
        cycle = list(cycle)
        rotations = [tuple(cycle[i:] + cycle[:i]) for i in range(len(cycle))]
        return min(rotations)

    def enumerate_cycles(self, max_length=3, max_candidates=350):
        """Enumerate deterministic 2/3-cycle candidates with a Render-safe cap."""
        cycles = []
        seen = set()
        nodes = sorted(self.kx.nodes)

        for u in nodes:
            for v in sorted(self.kx.adj_list.get(u, [])):
                if u < v and u in self.kx.adj_list.get(v, []):
                    key = self._canonical_cycle([u, v])
                    if key not in seen:
                        seen.add(key)
                        cycles.append(key)
                        if len(cycles) >= max_candidates:
                            return cycles

        if max_length >= 3:
            for u in nodes:
                for v in sorted(self.kx.adj_list.get(u, [])):
                    if v == u:
                        continue
                    for w in sorted(self.kx.adj_list.get(v, [])):
                        if w in (u, v):
                            continue
                        if u in self.kx.adj_list.get(w, []):
                            key = self._canonical_cycle([u, v, w])
                            if key not in seen:
                                seen.add(key)
                                cycles.append(key)
                                if len(cycles) >= max_candidates:
                                    return cycles
        return cycles

    def build_candidates(self, max_length=3, max_candidates=350):
        self.candidates = {}
        for idx, cycle in enumerate(self.enumerate_cycles(max_length, max_candidates), start=1):
            edges = self._cycle_edges(cycle)
            pref_gain = 0
            priority = 0
            for donor_pair, recipient_pair in edges:
                pref_gain += self._preference_score(recipient_pair, donor_pair)
                priority += self._patient_priority(recipient_pair)

            transplant_count = len(cycle)
            stability_margin = pref_gain / transplant_count
            weight = (10 * transplant_count) + pref_gain + priority + stability_margin
            candidate = CycleCandidate(
                id=f"X{idx}",
                nodes=tuple(cycle),
                edges=edges,
                weight=round(weight, 4),
                transplant_count=transplant_count,
                preference_gain=round(pref_gain, 4),
                stability_margin=round(stability_margin, 4),
            )
            self.candidates[candidate.id] = candidate
        return self.candidates

    def _hospital(self, pair_id: str, num_hospitals: int) -> int:
        key = (pair_id, num_hospitals)
        if key not in self.hospital_cache:
            self.hospital_cache[key] = self._stable_bucket(pair_id, num_hospitals)
        return self.hospital_cache[key]

    def _resource_conflict(self, a: CycleCandidate, b: CycleCandidate, num_hospitals: int) -> bool:
        for u in a.nodes:
            for v in b.nodes:
                if (self._hospital(u, num_hospitals) == self._hospital(v, num_hospitals) and
                        self.kx.nodes[u]['donor'] == self.kx.nodes[v]['donor']):
                    return True
        return False

    def build_conflict_graph(self, num_hospitals=6):
        ids = list(self.candidates)
        self.conflict_adj = {cid: set() for cid in ids}
        conflict_edges = []

        for i, aid in enumerate(ids):
            a = self.candidates[aid]
            a_nodes = set(a.nodes)
            for bid in ids[i + 1:]:
                b = self.candidates[bid]
                overlap = bool(a_nodes & set(b.nodes))
                resource = self._resource_conflict(a, b, num_hospitals)
                if overlap or resource:
                    self.conflict_adj[aid].add(bid)
                    self.conflict_adj[bid].add(aid)
                    conflict_edges.append({'from': aid, 'to': bid, 'type': 'overlap' if overlap else 'resource'})
        return conflict_edges

    def kernelise(self, top_per_patient=12):
        """Practical kernel: remove dominated duplicate cycles and cap patient-local choices."""
        active = set(self.candidates)
        removed = set()
        best_by_node_set = {}

        for cid, cand in self.candidates.items():
            key = frozenset(cand.nodes)
            old = best_by_node_set.get(key)
            if old is None or cand.weight > self.candidates[old].weight:
                if old is not None:
                    removed.add(old)
                best_by_node_set[key] = cid
            else:
                removed.add(cid)

        active -= removed
        patient_to_cycles = {}
        for cid in active:
            for node in self.candidates[cid].nodes:
                patient_to_cycles.setdefault(node, []).append(cid)

        for node, ids in patient_to_cycles.items():
            ranked = sorted(ids, key=lambda cid: self.candidates[cid].weight, reverse=True)
            removed.update(ranked[top_per_patient:])

        active -= removed
        forced = set()
        for cid in list(active):
            if not (self.conflict_adj.get(cid, set()) & active):
                forced.add(cid)
                active.remove(cid)

        blocked_by_forced = set()
        for cid in forced:
            blocked_by_forced |= self.conflict_adj.get(cid, set()) & active
        active -= blocked_by_forced
        removed |= blocked_by_forced

        return active, forced, removed

    def _can_add(self, cid, chosen):
        return not (self.conflict_adj.get(cid, set()) & chosen)

    def solve_greedy(self, candidate_ids=None):
        start = time.perf_counter()
        ids = candidate_ids or set(self.candidates)
        chosen = []
        blocked = set()

        for cid in sorted(ids, key=lambda x: self.candidates[x].weight, reverse=True):
            if cid in blocked:
                continue
            chosen.append(cid)
            blocked |= self.conflict_adj.get(cid, set())

        elapsed = (time.perf_counter() - start) * 1000
        return self._solution_payload(chosen, elapsed)

    def solve_fpt(self, max_depth=30, top_per_patient=12):
        start = time.perf_counter()
        kernel, forced, removed = self.kernelise(top_per_patient=top_per_patient)
        kernel_ids = sorted(kernel, key=lambda cid: self.candidates[cid].weight, reverse=True)
        suffix = [0] * (len(kernel_ids) + 1)
        for i in range(len(kernel_ids) - 1, -1, -1):
            suffix[i] = suffix[i + 1] + self.candidates[kernel_ids[i]].weight

        def greedy_complete(start_index, chosen, weight):
            completed = set(chosen)
            completed_weight = weight
            for cid in kernel_ids[start_index:]:
                if self._can_add(cid, completed):
                    completed.add(cid)
                    completed_weight += self.candidates[cid].weight
            return completed, completed_weight

        seed_ids, seed_weight = greedy_complete(
            0,
            set(forced),
            sum(self.candidates[cid].weight for cid in forced),
        )
        best = {'ids': seed_ids, 'weight': seed_weight}

        def search(index, chosen, weight, depth):
            if index >= len(kernel_ids) or depth >= max_depth:
                completed, completed_weight = greedy_complete(index, chosen, weight)
                if completed_weight > best['weight']:
                    best['ids'] = completed
                    best['weight'] = completed_weight
                return
            if weight + suffix[index] <= best['weight']:
                return

            cid = kernel_ids[index]
            if self._can_add(cid, chosen):
                search(
                    index + 1,
                    chosen | {cid},
                    weight + self.candidates[cid].weight,
                    depth + 1,
                )
            search(index + 1, chosen, weight, depth + 1)

        search(0, set(forced), best['weight'], 0)
        elapsed = (time.perf_counter() - start) * 1000
        payload = self._solution_payload(best['ids'], elapsed)
        payload.update({
            'kernel_size': len(kernel),
            'original_size': len(self.candidates),
            'kernel_reduction': round((1 - len(kernel) / max(len(self.candidates), 1)) * 100, 1),
            'forced_in': len(forced),
            'removed': len(removed),
        })
        return payload

    def _current_assignment_scores(self, chosen_ids):
        scores = {}
        assigned = {}
        for cid in chosen_ids:
            for donor_pair, recipient_pair in self.candidates[cid].edges:
                score = self._preference_score(recipient_pair, donor_pair)
                scores[recipient_pair] = score
                assigned[recipient_pair] = donor_pair
        return scores, assigned

    def count_stability_violations(self, chosen_ids):
        chosen = set(chosen_ids)
        current_scores, _ = self._current_assignment_scores(chosen)
        violations = []

        for cid, cand in self.candidates.items():
            if cid in chosen:
                continue
            blockers = []
            for donor_pair, recipient_pair in cand.edges:
                proposed = self._preference_score(recipient_pair, donor_pair)
                current = current_scores.get(recipient_pair, 0)
                if proposed <= current + 0.001:
                    blockers = []
                    break
                blockers.append(recipient_pair)
            if blockers:
                violations.append(cid)

        return violations

    def _solution_payload(self, chosen_ids, elapsed_ms):
        chosen = sorted(chosen_ids, key=lambda cid: self.candidates[cid].id)
        violations = self.count_stability_violations(chosen)
        cycles = [self._candidate_payload(self.candidates[cid]) for cid in chosen]
        return {
            'solution': chosen,
            'cycles': cycles,
            'size': len(chosen),
            'transplants': sum(self.candidates[cid].transplant_count for cid in chosen),
            'weight': round(sum(self.candidates[cid].weight for cid in chosen), 4),
            'stability_violations': len(violations),
            'blocking_cycles': violations[:8],
            'time_ms': round(elapsed_ms, 4),
        }

    def _candidate_payload(self, cand: CycleCandidate):
        return {
            'id': cand.id,
            'nodes': list(cand.nodes),
            'edges': [{'from': u, 'to': v} for u, v in cand.edges],
            'weight': cand.weight,
            'transplants': cand.transplant_count,
            'preference_gain': cand.preference_gain,
            'stability_margin': cand.stability_margin,
        }

    def run(self, max_length=3, max_candidates=350, num_hospitals=6, top_per_patient=12):
        start = time.perf_counter()
        self.build_candidates(max_length=max_length, max_candidates=max_candidates)
        conflict_edges = self.build_conflict_graph(num_hospitals=num_hospitals)
        greedy = self.solve_greedy()
        fpt = self.solve_fpt(top_per_patient=top_per_patient)
        if greedy['weight'] > fpt['weight']:
            kernel_stats = {
                'kernel_size': fpt.get('kernel_size', len(self.candidates)),
                'original_size': fpt.get('original_size', len(self.candidates)),
                'kernel_reduction': fpt.get('kernel_reduction', 0),
                'forced_in': fpt.get('forced_in', 0),
                'removed': fpt.get('removed', 0),
                'time_ms': fpt.get('time_ms', 0),
                'used_greedy_fallback': True,
            }
            fpt = dict(greedy)
            fpt.update(kernel_stats)
        else:
            fpt['used_greedy_fallback'] = False
        elapsed = (time.perf_counter() - start) * 1000

        selected_edges = []
        for cycle in fpt['cycles']:
            selected_edges.extend(cycle['edges'])

        top_candidates = sorted(
            (self._candidate_payload(c) for c in self.candidates.values()),
            key=lambda c: c['weight'],
            reverse=True,
        )[:10]

        return {
            'algorithm': 'PS-KCP',
            'candidate_count': len(self.candidates),
            'cycle_conflict_edges': len(conflict_edges),
            'greedy': greedy,
            'fpt': fpt,
            'weight_improvement': round(fpt['weight'] - greedy['weight'], 4),
            'transplant_improvement': fpt['transplants'] - greedy['transplants'],
            'stability_improvement': greedy['stability_violations'] - fpt['stability_violations'],
            'selected_edges': selected_edges,
            'selected_nodes': sorted({node for cycle in fpt['cycles'] for node in cycle['nodes']}),
            'top_candidates': top_candidates,
            'total_time_ms': round(elapsed, 4),
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
