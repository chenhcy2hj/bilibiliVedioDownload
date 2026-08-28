"""pytest 夹具：测试使用独立数据目录，隔离用户真实数据（Cookie/设置等）。"""
import os
import shutil
import tempfile

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="bili_test_data_")
os.environ["BILIDL_DATA_DIR"] = _TEST_DATA_DIR


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)