#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Convert browser cookie string to Netscape cookie format for yt-dlp
"""

# Read the original cookie file
with open('bilibiliCookie.txt', 'r') as f:
    cookie_str = f.read().strip()

# Parse the cookie string
cookies = []
for item in cookie_str.split(';'):
    item = item.strip()
    if '=' in item:
        name, value = item.split('=', 1)
        cookies.append((name.strip(), value.strip()))

# Write in Netscape format
with open('bilibiliCookie_netscape.txt', 'w') as f:
    # Write header
    f.write("# Netscape HTTP Cookie File\n")
    f.write("# https://curl.haxx.se/rfc/cookie_spec.html\n")
    f.write("# This is a generated file! Do not edit.\n\n")

    # Write each cookie
    for name, value in cookies:
        # Format: domain	flag	path	secure	expiry	name	value
        # Domain: .bilibili.com (leading dot means it's valid for subdomains)
        # Flag: TRUE (valid for all hosts in domain)
        # Path: /
        # Secure: FALSE (can be sent over HTTP)
        # Expiry: 0 (session cookie)
        f.write(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}\n")

print(f"Converted {len(cookies)} cookies to Netscape format")
print("Saved to: bilibiliCookie_netscape.txt")
