# Copyright (c) First Placement by Vipul Sharma
# Core logical engine for Kidney Exchange Visualizer

import json
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
                # If the dataset is too big, taking a subset might be better for cycle finding
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
        rules = {
            'O': ['O', 'A', 'B', 'AB'],
            'A': ['A', 'AB'],
            'B': ['B', 'AB'],
            'AB': ['AB']
        }
        return recipient in rules.get(donor, [])
        
    def build_graph(self):
        self.adj_list = {u: [] for u in self.nodes}
        for u, u_data in self.nodes.items():
            for v, v_data in self.nodes.items():
                if u != v:
                    if self.can_donate(u_data['donor'], v_data['recipient']):
                        self.adj_list[u].append(v)
                        
    def find_cycles(self, max_length=3):
        cycles = []
        def dfs(start, current, path):
            if len(path) > max_length:
                return
            for neighbor in self.adj_list.get(current, []):
                if neighbor == start:
                    if 2 <= len(path) <= max_length:
                        cycles.append(path)
                elif neighbor not in path:
                    dfs(start, neighbor, path + [neighbor])
                    
        for node in self.nodes:
            dfs(node, node, [node])
            
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
        matching = []
        for i in range(len(cycle)):
            u = cycle[i]
            v = cycle[(i + 1) % len(cycle)]
            matching.append((u, v))
        return matching
        
    def is_induced_matching(self, cycle):
        # We benchmark multiple iterations inside to amplify the time since doing it once is too fast
        matching = set(self.extract_matching(cycle))
        cycle_nodes = set(cycle)
        
        start_t = time.perf_counter()
        for _ in range(100): # amplify
            is_induced = True
            for u in cycle_nodes:
                for v in self.adj_list[u]:
                    if v in cycle_nodes:
                        if (u, v) not in matching:
                            is_induced = False
                            break
        end_t = time.perf_counter()
        
        return is_induced, end_t - start_t
        
    def is_acyclic_matching(self, matching):
        adj = {u: [] for u, v in matching}
        for u, v in matching:
            adj[u].append(v)
            if v not in adj:
                adj[v] = []
                
        start_t = time.perf_counter()
        for _ in range(100): # amplify
            visited = set()
            in_stack = set()
            is_acyclic = True
            
            def has_cycle(node):
                if node in in_stack: return True
                if node in visited: return False
                visited.add(node)
                in_stack.add(node)
                for neighbor in adj.get(node, []):
                    if has_cycle(neighbor): return True
                in_stack.remove(node)
                return False
                
            for node in adj:
                if node not in visited:
                    if has_cycle(node):
                        is_acyclic = False
                        break
        end_t = time.perf_counter()
        
        return is_acyclic, end_t - start_t
