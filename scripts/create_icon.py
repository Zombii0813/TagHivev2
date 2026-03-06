import struct
import os

# ICO Header
ico_header = struct.pack('<HHH', 0, 1, 1)  # Reserved, Type (1=ICO), Count

# Icon directory entry (16 bytes)
ico_entry = struct.pack('<BBBBHHII', 32, 32, 0, 0, 1, 32, 40+4, 22)

# BMP Header (BITMAPINFOHEADER)
bmp_header = struct.pack('<IIIHHIIIIII', 40, 32, 64, 1, 32, 0, 4, 0, 0, 0, 0)

# One 32-bit pixel (BGRA)
pixel = struct.pack('<BBBB', 0, 0, 255, 255)

# 确保目录存在
os.makedirs('src-tauri/icons', exist_ok=True)

with open('src-tauri/icons/icon.ico', 'wb') as f:
    f.write(ico_header)
    f.write(ico_entry)
    f.write(bmp_header)
    f.write(pixel)

print('Icon created successfully')
