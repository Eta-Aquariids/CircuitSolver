import numpy as np

class Unit:
    def __init__(self, nodes, a, b, c):
        """
        用nodes, a, b, c初始化Unit类
        i: nodes[0] -> nodes[1]; u: nodes[0]-nodes[1]
        a*i + b*u = c 线性元件
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
        vector -= self.c
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
        vector -= self.c
        return vector, 0


def solver(units, nodes, sum_nodes, sum_units):
    """解线性方程组（未知量 x = [各支路电流..., 各节点电压...]）。

    row 0            : 参考节点电压 = 0（节点 0 就是 0 V 参考点）
    row 1..m         : 各支路 KVL， a*i + b*(u0-u1) = c
    row m+i, 1<=i<n  : 各非参考节点 KCL
    解完把电流写回 unit.i、电压写回 nodes[]
    """
    A = np.zeros((sum_units + sum_nodes, sum_units + sum_nodes))
    b = np.zeros(sum_units + sum_nodes)
    A[0, sum_units] = 1
    for i, unit in enumerate(units):
        A[i + 1, :], b[i + 1] = unit.kvl(i, sum_units, sum_nodes)
    for i in range(1, sum_nodes):
        for j, unit in enumerate(units):
            vector = unit.kcl(j, i, sum_units, sum_nodes)
            A[sum_units + i, :] += vector
    x = np.linalg.solve(A, b)
    for i, unit in enumerate(units):
        unit.i = x[i]
    for j in range(sum_nodes):
        nodes[j] = x[sum_units + j]
    print("Solution x:", x)
