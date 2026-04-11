import inspect

from app import main


def test_recover_interrupted_tasks_includes_yasa():
    source = inspect.getsource(main.recover_interrupted_tasks)
    assert "YasaScanTask" in source
    assert "RECOVERABLE_YASA_TASK_STATUSES" in source
    assert "PmdScanTask" in source
    assert "RECOVERABLE_PMD_TASK_STATUSES" in source


def test_recoverable_yasa_statuses():
    assert getattr(main, "RECOVERABLE_YASA_TASK_STATUSES", None) == {"pending", "running"}
    assert getattr(main, "RECOVERABLE_PMD_TASK_STATUSES", None) == {"pending", "running"}
