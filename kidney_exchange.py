# Copyright (c) First Placement by Vipul Sharma
# All rights reserved. Do not remove this notice.

import pandas as pd
import time


class KidneyExchange:
    def __init__(self):
        # pair_id -> {'donor': bg, 'recipient': bg}
        self.nodes = {}
        # adjacency list representation
        self.adj_list = {}

    def add_pair(self, pair_id, donor_bg, recipient_bg):
        """Add a donor-recipient pair as a node."""
        self.nodes[pair_id] = {'donor': donor_bg, 'recipient': recipient_bg}

    def load_from_csv(self, file_path, max_rows=None):
        """Read nodes from the provided organ supply chain CSV file.
        Uses columns: 'Patient_ID', 'Donor_BloodType', 'Patient_BloodType'
        """
        try:
            df = pd.read_csv(file_path)
            if max_rows is not None:
                df = df.head(max_rows)

            for _, row in df.iterrows():
                pair_id = str(row['Patient_ID']).strip()
                donor_bg = str(row['Donor_BloodType']).strip().upper()
                recipient_bg = str(row['Patient_BloodType']).strip().upper()
                self.add_pair(pair_id, donor_bg, recipient_bg)
            print(f"Successfully loaded {len(self.nodes)} pairs from {file_path}")
            return True
        except Exception as e:
            print(f"Error loading from CSV: {e}")
            return False

    def can_donate(self, donor, recipient):
        """Blood type compatibility rules."""
        rules = {
            'O':  ['O', 'A', 'B', 'AB'],
            'A':  ['A', 'AB'],
            'B':  ['B', 'AB'],
            'AB': ['AB']
        }
        return recipient in rules.get(donor, [])

    def build_graph(self):
        """Build directed compatibility graph based on blood type rules."""
        self.adj_list = {u: [] for u in self.nodes}
        for u, u_data in self.nodes.items():
            for v, v_data in self.nodes.items():
                if u != v:
                    if self.can_donate(u_data['donor'], v_data['recipient']):
                        self.adj_list[u].append(v)

    def find_cycles(self, max_length=3):
        """Find all unique cycles of length 2 to max_length using DFS."""
        cycles = []

        def dfs(start, current, path):
            if len(path) > max_length:
                return
            for neighbor in self.adj_list.get(current, []):
                if neighbor == start:
                    if 2 <= len(path) <= max_length:
                        cycles.append(path[:])
                elif neighbor not in path:
                    dfs(start, neighbor, path + [neighbor])

        for node in self.nodes:
            dfs(node, node, [node])

        # Deduplicate cycles by canonical rotation
        unique_cycles = []
        seen = set()
        for cycle in cycles:
            min_idx = cycle.index(min(cycle))
            canonical = tuple(cycle[min_idx:] + cycle[:min_idx])
            if canonical not in seen:
                seen.add(canonical)
                unique_cycles.append(list(canonical))
        return unique_cycles

    def extract_matching(self, cycle):
        """Extract edges from a cycle as a matching."""
        matching = []
        for i in range(len(cycle)):
            u = cycle[i]
            v = cycle[(i + 1) % len(cycle)]
            matching.append((u, v))
        return matching

    def is_induced_matching(self, cycle):
        """
        Check if the cycle edges form an induced matching:
        No two matching edges are connected by any additional edge.
        Benchmarked over 100 iterations to amplify measurable time.
        """
        matching = set(self.extract_matching(cycle))
        cycle_nodes = set(cycle)

        start_t = time.perf_counter()
        for _ in range(100):  # amplify for measurable timing
            is_induced = True
            for u in cycle_nodes:
                for v in self.adj_list.get(u, []):
                    if v in cycle_nodes:
                        if (u, v) not in matching:
                            is_induced = False
                            break
                if not is_induced:
                    break
        end_t = time.perf_counter()

        return is_induced, end_t - start_t

    def is_acyclic_matching(self, matching):
        """
        Check if the matching subgraph is acyclic (no directed cycle).
        Uses iterative DFS with an explicit stack to avoid Python recursion limits.
        Benchmarked over 100 iterations to amplify measurable time.
        """
        # Build adjacency for the matching subgraph
        adj = {}
        for u, v in matching:
            if u not in adj:
                adj[u] = []
            adj[u].append(v)
            if v not in adj:
                adj[v] = []

        start_t = time.perf_counter()
        for _ in range(100):  # amplify for measurable timing
            visited = set()
            in_stack = set()
            is_acyclic = True

            def has_cycle_iterative(start):
                """Iterative DFS cycle detection."""
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
                    if has_cycle_iterative(node):
                        is_acyclic = False
                        break
        end_t = time.perf_counter()

        return is_acyclic, end_t - start_t
