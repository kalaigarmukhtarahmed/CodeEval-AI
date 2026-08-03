import pytest
from calculator import add, divide


def test_add_positive():
    assert add(2, 3) == 5


def test_add_negative():
    assert add(-1, -1) == -2


def test_divide_valid():
    assert divide(10, 2) == 5


def test_divide_by_zero():
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)


def test_intentional_failure():
    assert add(2, 2) == 5
