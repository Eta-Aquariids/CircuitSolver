import numpy as np

class Unit:
    def __init__(self, nodes, a, b, c):
        """
        Initialize the Units class with nodes, a, b, and c values.
        i: nodes[0] -> nodes[1]; u: nodes[0]-nodes[1]
        a*i + b*u = c linear unit model
        """
        self.nodes = nodes
        self.a = a
        self.b = b
        self.c = c
        self.i = np.nan

    def kvl(self, unit_id, sum_units, sum_nodes):
        vector = np.zeros(sum_units + sum_nodes)
        vector[unit_id] = self.a
        vector[self.nodes[0] + sum_units] = self.b
        vector[self.nodes[1] + sum_units] = - self.b
        return vector, self.c

    def kcl(self, unit_id, node_id, sum_units, sum_nodes):
        vector = np.zeros(sum_units + sum_nodes)
        if self.nodes[0] == node_id:
            vector[unit_id] = -1
        elif self.nodes[1] == node_id:
            vector[unit_id] = 1
        return vector