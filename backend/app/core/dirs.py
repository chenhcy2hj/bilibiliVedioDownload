"""数据目录初始化与旧数据迁移（M5）。

- ensure_data_dirs：创建数据目录与默认子目录（打包模式首次启动时执行）；
- migrate_legacy_data：打包模式下旧数据目录存在且新目录为空时迁移一次。
"""
import logging
import shutil

from app.config import DATA_DIR, DEFAULT_OUTPUT_DIR, LEGACY_DATA_DIRS

logger = logging.getLogger(__name__)


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_data(frozen: bool = False) -> None:
    """打包模式首次启动：旧数据目录有内容且新目录为空 → 复制（仅一次）。

    非打包模式（开发）不迁移。
    """
    if not frozen:
        return
    ensure_data_dirs()
    if any(DATA_DIR.iterdir()):
        return  # 新目录已有数据，跳过（避免重复搬移）
    for legacy in LEGACY_DATA_DIRS:
        if not legacy.exists():
            continue
        for item in legacy.iterdir():
            try:
                target = DATA_DIR / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
                logger.info("迁移旧数据: %s -> %s", item, target)
            except OSError:
                logger.warning("迁移失败（跳过）: %s", item)