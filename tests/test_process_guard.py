from unittest.mock import MagicMock, patch

from utils.process_guard import ensure_single_instance


def test_ensure_single_instance_kills_other_main_py_processes():
    with (
        patch("utils.process_guard.os.getpid", return_value=1000),
        patch(
            "utils.process_guard.subprocess.run",
            return_value=MagicMock(
                stdout=(
                    "  PID  PPID COMMAND\n"
                    " 1000  1234 python /root/plan-mode-project/main.py\n"
                    " 2001  1235 python /root/plan-mode-project/main.py\n"
                    " 3001  1236 python /some/other/main.py\n"
                    " 4001  1237 python /root/plan-mode-project/run.py\n"
                ),
                returncode=0,
            ),
        ) as mock_run,
        patch("utils.process_guard.os.kill") as mock_kill,
        patch("utils.process_guard.time.sleep") as mock_sleep,
    ):
        killed = ensure_single_instance()

    mock_run.assert_called_once()
    assert killed == [2001]
    mock_kill.assert_called_once_with(2001, 9)
    mock_sleep.assert_called_once_with(1)


def test_ensure_single_instance_no_others():
    with (
        patch("utils.process_guard.os.getpid", return_value=1000),
        patch(
            "utils.process_guard.subprocess.run",
            return_value=MagicMock(
                stdout=(
                    "  PID  PPID COMMAND\n"
                    " 1000  1234 python /root/plan-mode-project/main.py\n"
                ),
                returncode=0,
            ),
        ),
        patch("utils.process_guard.os.kill") as mock_kill,
        patch("utils.process_guard.time.sleep") as mock_sleep,
    ):
        killed = ensure_single_instance()

    assert killed == []
    mock_kill.assert_not_called()
    mock_sleep.assert_not_called()


def test_ensure_single_instance_handles_missing_process():
    with (
        patch("utils.process_guard.os.getpid", return_value=1000),
        patch(
            "utils.process_guard.subprocess.run",
            return_value=MagicMock(
                stdout=(
                    "  PID  PPID COMMAND\n"
                    " 1000  1234 python /root/plan-mode-project/main.py\n"
                    " 2001  1235 python /root/plan-mode-project/main.py\n"
                ),
                returncode=0,
            ),
        ),
        patch(
            "utils.process_guard.os.kill",
            side_effect=[ProcessLookupError, None],
        ) as mock_kill,
        patch("utils.process_guard.time.sleep") as mock_sleep,
    ):
        killed = ensure_single_instance()

    assert killed == []
    assert mock_kill.call_count == 1
    mock_sleep.assert_not_called()
