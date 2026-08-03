from app import run_app
from services import get_service_name
from performance import process_file_data, sort_numbers, calculate_heavy

def test_app():
    assert run_app() == "Phase10 Service"

def test_service():
    assert get_service_name() == "Phase10 Service"

def test_process_file_data(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello", encoding="utf-8")
    assert process_file_data([str(f)]) is True

def test_sort_numbers():
    assert sort_numbers([3, 1, 2]) == [1, 2, 3]

def test_calculate_heavy():
    assert calculate_heavy(2, 3) == 32
