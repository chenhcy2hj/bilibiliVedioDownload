"""设置模块测试：默认值、绝对路径校验、自动创建、不可写、持久化。"""
from pathlib import Path

import pytest

from app.api.errors import ApiError
from app.core.settings.service import SettingsService


def make_service(tmp_path: Path) -> SettingsService:
    return SettingsService(
        settings_file=tmp_path / "settings.json",
        default_output_dir=tmp_path / "default_out",
    )


class TestDefaults:
    def test_default_output_dir(self, tmp_path):
        svc = make_service(tmp_path)
        assert svc.get_output_dir() == tmp_path / "default_out"

    def test_no_settings_file_created_by_default(self, tmp_path):
        svc = make_service(tmp_path)
        svc.get_settings()
        assert not (tmp_path / "settings.json").exists()


class TestSetOutputDir:
    def test_valid_absolute_path_created(self, tmp_path):
        svc = make_service(tmp_path)
        target = tmp_path / "music" / "sub"
        settings = svc.set_output_dir(str(target))
        assert settings["output_dir"] == str(target)
        assert target.is_dir()
        # 持久化
        assert (tmp_path / "settings.json").exists()

    def test_relative_path_rejected(self, tmp_path):
        svc = make_service(tmp_path)
        with pytest.raises(ApiError) as e:
            svc.set_output_dir("relative/path")
        assert e.value.code == "INVALID_PATH"
        assert e.value.status_code == 422

    def test_existing_file_rejected(self, tmp_path):
        svc = make_service(tmp_path)
        f = tmp_path / "a_file"
        f.write_text("x")
        with pytest.raises(ApiError) as e:
            svc.set_output_dir(str(f))
        assert e.value.code == "INVALID_PATH"

    def test_persist_and_reload(self, tmp_path):
        svc = make_service(tmp_path)
        target = tmp_path / "out2"
        svc.set_output_dir(str(target))
        svc2 = make_service(tmp_path)  # 重新加载
        assert svc2.get_output_dir() == target

    def test_corrupt_settings_file_falls_back(self, tmp_path):
        (tmp_path / "settings.json").write_text("{broken json", encoding="utf-8")
        svc = make_service(tmp_path)
        assert svc.get_output_dir() == tmp_path / "default_out"