import yt_dlp
import os

def extract_audio(url, output_dir="output", audio_format="mp3"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    cookie_file = "bilibiliCookie_netscape.txt"
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': False,
        'cookiefile': cookie_file,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '192',
        }],
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Referer': 'https://www.bilibili.com',
        },
        'extractargs': {
            'bilibili': {
                'prefer_multi_flv': False,
            }
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


if __name__ == "__main__":
    urls = [
        "https://www.bilibili.com/video/BV1PN411P7RZ",
        "https://www.bilibili.com/video/BV17t4y1N72d",
        "https://www.bilibili.com/video/BV1u14y1b7rf",
        "https://www.bilibili.com/video/BV1CQFjeGEaZ",
        "https://www.bilibili.com/video/BV1ha4y1d7yo",
        "https://www.bilibili.com/video/BV1hk4y1W76R",
        "https://www.bilibili.com/video/BV1oQ4y1v7PB",
        "https://www.bilibili.com/video/BV1us411k7qa",
        "https://www.bilibili.com/video/BV1eG411C755",
        "https://www.bilibili.com/video/BV1M16QYvEUT",
        "https://www.bilibili.com/video/BV1hu411v78W",
        "https://www.bilibili.com/video/BV1Kv411q7D2",
        "https://www.bilibili.com/video/BV1FE411q7et",
        "https://www.bilibili.com/video/BV12a411k7os",
        "https://www.bilibili.com/video/BV1K4411K77X",
        "https://www.bilibili.com/video/BV1K4411K78H",
        "https://www.bilibili.com/video/BV1Y4411N7mj",
        "https://www.bilibili.com/video/BV1gW411b735",
        "https://www.bilibili.com/video/BV1r7411p7R4",
        "https://www.bilibili.com/video/BV1ox4y1x7rd",
        "https://www.bilibili.com/video/BV1S1qpB6ELk",
    ]
    for url in urls:
        print(f"\n{'='*60}")
        print(f"Downloading: {url}")
        print(f"{'='*60}")
        try:
            extract_audio(url)
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            continue
