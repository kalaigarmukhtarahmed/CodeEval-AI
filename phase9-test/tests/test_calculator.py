import pytest


def add(a, b):
    return a + b


def test_add_1():
    assert add(1, 1) == 2


def test_add_2():
    assert add(2, 3) == 5


def test_add_3():
    assert add(10, 0) == 10
