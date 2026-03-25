# Python Basics 1 - NumPy Matrix Operations

## Tasks

Create a 9x8 matrix `M` with `np.float64` dtype, filled with values 1 to 72.

Then create the following logical index arrays:

1. `L1`: Elements of M greater than 8
2. `L2`: Elements of M divisible by 3
3. `L3`: Elements of M that are even AND greater than 20
4. `L4`: Rows where ALL elements are greater than 16
5. `L5`: Columns where ANY element is divisible by 9

Use `np.where`, `np.all`, and `np.any` where appropriate.

## Requirements

- All variables must be defined in `solution.py`
- Matrix M must have dtype `np.float64`
- Use NumPy operations (no Python loops)
