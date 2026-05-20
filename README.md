# Bilibili Audio Downloader

从B站视频下载音频并转换为MP3格式。

## 前置准备

### 1. Python 3

确保系统已安装 Python 3：

```bash
python3 --version
```

### 2. FFmpeg

音频转码依赖 FFmpeg，需提前安装：

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# 从 https://ffmpeg.org/download.html 下载并添加到 PATH
```

### 3. yt-dlp

建议在虚拟环境中安装：

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install yt-dlp
```

### 4. B站Cookie

由于B站反爬机制，必须提供登录Cookie才能下载。

**获取Cookie步骤：**

1. 在浏览器中登录 [bilibili.com](https://www.bilibili.com)
2. 按 `F12` 打开开发者工具 → `Network` 标签
3. 刷新页面，点击任意请求，在请求头中找到 `Cookie` 字段
4. 复制完整的Cookie值，保存到 `bilibiliCookie.txt` 文件中

**Cookie文件格式：** 一行纯文本，格式如：

```
key1=value1; key2=value2; key3=value3
```

**转换为yt-dlp可用格式：**

```bash
python3 convert_cookie.py
```

这会生成 `bilibiliCookie_netscape.txt`，供下载脚本使用。

> Cookie有效期有限，如遇到412错误，请重新获取Cookie。

## 使用方法

### 下载单个视频

编辑 `installVideo.py` 底部的URL：

```python
if __name__ == "__main__":
    url = "https://www.bilibili.com/video/BVxxxxxxxx"
    extract_audio(url)
```

然后运行：

```bash
source venv/bin/activate   # Windows: venv\Scripts\activate
python installVideo.py
```

### 批量下载

将多个URL填入列表：

```python
if __name__ == "__main__":
    urls = [
        "https://www.bilibili.com/video/BV1PN411P7RZ",
        "https://www.bilibili.com/video/BV17t4y1N72d",
        # ... 更多URL
    ]
    for url in urls:
        extract_audio(url)
```

### 输出

音频文件保存在 `output/` 目录下，默认格式为 MP3（192kbps）。

## 文件说明

| 文件 | 说明 |
|------|------|
| `installVideo.py` | 主脚本，下载B站视频并提取音频 |
| `convert_cookie.py` | 将浏览器Cookie转换为Netscape格式 |
| `bilibiliCookie.txt` | 从浏览器获取的原始Cookie（需自行创建，不上传至仓库） |
| `bilibiliCookie_netscape.txt` | 转换后的Cookie（自动生成，不上传至仓库） |
| `output/` | 音频输出目录 |
