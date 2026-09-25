import unit
import numpy as np

def circuit_init():
    units = []
    units.append(unit.Unit([0, 1], 2, -1, 0))
    units.append(unit.Unit([0, 2], 2, -1, 0))
    units.append(unit.Unit([1, 2], 0, 1, -4))
    units.append(unit.Unit([2, 4], 4, -1, 0))
    units.append(unit.Unit([2, 3], 3, -1, 0))
    units.append(unit.Unit([3, 4], 2, -1, 0))
    units.append(unit.Unit([0, 4], 1, 0, 9))
    sum_nodes = 5
    sum_units = 7
    return units, sum_nodes, sum_units


def main():
    units, sum_nodes, sum_units = circuit_init()
    nodes= np.zeros(sum_nodes)
    A = np.zeros((sum_units + sum_nodes, sum_units + sum_nodes))
    b = np.zeros(sum_units + sum_nodes)
    A[0,sum_units] = 1
    for i, unit in enumerate(units):
        A[i+1, :], b[i+1] = unit.kvl(i, sum_units, sum_nodes)
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

if __name__ == "__main__":
    main()