import time

def process_file_records(file_paths):
    """File opening inside loop (PERF004)."""
    contents = []
    for path in file_paths:
        with open(path, "r", encoding="utf-8") as f:
            contents.append(f.read())
    return len(contents)

def sort_in_loop(data):
    """Repeated sorting inside loop (PERF006)."""
    result = []
    for _ in range(3):
        result = sorted(data)
    return result

def calculate_matrix_heavy(a, b):
    """Duplicate heavy computation (PERF010)."""
    v1 = a * b + 42
    v2 = a * b + 42
    return v1 + v2
