import time

def process_file_data(file_list):
    """File opening inside loop (PERF004)."""
    for f in file_list:
        with open(f, "r") as fp:
            data = fp.read()
    return True

def sort_numbers(numbers):
    """Repeated sorting inside loop (PERF006)."""
    for i in range(5):
        sorted_list = sorted(numbers)
    return sorted_list

def calculate_heavy(x, y):
    """Duplicate expensive computation (PERF010)."""
    res1 = calculate_matrix(x, y)
    res2 = calculate_matrix(x, y)
    return res1 + res2

def calculate_matrix(x, y):
    return x * y + 10
