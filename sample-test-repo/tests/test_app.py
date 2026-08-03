from main import start_application
from services import get_app_info, fetch_users_batch
from performance import process_file_records, sort_in_loop, calculate_matrix_heavy
from db import query_user_by_name

def test_start_application():
    info = start_application()
    assert info["name"] == "Sample App"

def test_get_app_info():
    info = get_app_info()
    assert info["version"] == "1.0.0"

def test_fetch_users_batch():
    users = fetch_users_batch([1, 2])
    assert len(users) == 2

def test_process_file_records(tmp_path):
    f = tmp_path / "sample.txt"
    f.write_text("test data", encoding="utf-8")
    assert process_file_records([str(f)]) == 1

def test_sort_in_loop():
    assert sort_in_loop([5, 2, 8]) == [2, 5, 8]

def test_calculate_matrix_heavy():
    assert calculate_matrix_heavy(3, 4) == 108

def test_query_user_by_name():
    q = query_user_by_name(None, "alice")
    assert "alice" in q
