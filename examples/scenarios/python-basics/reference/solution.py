import numpy as np

M = np.arange(1, 73, dtype=np.float64).reshape(9, 8)

L1 = M > 8
L2 = M % 3 == 0
L3 = (M % 2 == 0) & (M > 20)
L4 = np.all(M > 16, axis=1)
L5 = np.any(M % 9 == 0, axis=0)
