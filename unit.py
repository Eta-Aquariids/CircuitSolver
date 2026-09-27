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


class Resistor(Unit):
    def __init__(self, nodes, R):
        super().__init__(nodes, a=R, b=-1, c=0)


class VoltageSource(Unit):
    """
    nodes[0]- nodes[1]+
    """
    def __init__(self, nodes, U):
        super().__init__(nodes, a=0, b=-1, c=U)


class CurrentSource(Unit):
    """
    nodes[0]-> nodes[1]
    """
    def __init__(self, nodes, I):
        super().__init__(nodes, a=1, b=0, c=I)

class ControlledVoltageSource(Unit):
    """
    control = [0,0,...,1,...0]
    """
    def __init__(self, nodes, control):
        super().__init__(nodes, a=0, b=-1, c=control)

    def kvl(self, unit_id, sum_units, sum_nodes):
        vector = np.zeros(sum_units + sum_nodes)
        vector[unit_id] = self.a
        vector[self.nodes[0] + sum_units] = self.b
        vector[self.nodes[1] + sum_units] = - self.b
        vector -= self.control
        return vector, 0    

class ControlledCurrentSource(Unit):
    """
    control = [0,0,...,1,...0]
    """
    def __init__(self, nodes, control):
        super().__init__(nodes, a=1, b=0, c=control)

    def kvl(self, unit_id, sum_units, sum_nodes):
        vector = np.zeros(sum_units + sum_nodes)
        vector[unit_id] = self.a
        vector[self.nodes[0] + sum_units] = self.b
        vector[self.nodes[1] + sum_units] = - self.b
        vector -= self.control
        return vector, 0 