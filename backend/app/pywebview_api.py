"""pywebview js_api：暴露给前端（window.pywebview.api.*）的桌面能力。"""


class DesktopApi:
    def choose_dir(self) -> str | None:
        """系统原生目录选择器；取消返回 None。"""
        import webview

        windows = webview.windows
        if not windows:
            return None
        result = windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        return result[0] if result else None