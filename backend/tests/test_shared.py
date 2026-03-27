import importlib


def test_import_multi_target_collector_not_none():
    from services.shared import multi_target_collector

    assert multi_target_collector is not None


def test_import_load_engine_not_none():
    from services.shared import load_engine

    assert load_engine is not None


def test_multi_target_collector_is_singleton():
    from services import shared as m1

    m2 = importlib.import_module("services.shared")
    assert m1.multi_target_collector is m2.multi_target_collector


def test_load_engine_is_singleton():
    from services import shared as m1

    m2 = importlib.import_module("services.shared")
    assert m1.load_engine is m2.load_engine
