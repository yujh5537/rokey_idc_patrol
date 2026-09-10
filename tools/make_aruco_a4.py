#!/usr/bin/env python3
"""A4 출력용 ArUco 시트 — DICT_5X5_250, 지정 ID를 300dpi로 배치.
실기 마커는 20mm지만 웹캠 대리 검증용은 크게(기본 60mm) 뽑는다.
사용: python3 tools/make_aruco_a4.py 1 8 17 [--mm 60]
"""
import sys

import cv2
import numpy as np

argv = sys.argv[1:]
mm = 60.0
if "--mm" in argv:
    k = argv.index("--mm")
    mm = float(argv[k + 1])
    argv = argv[:k] + argv[k + 2:]
ids = [int(x) for x in argv] or [1, 8, 17, 30, 56]

DPI = 300
px = int(round(mm / 25.4 * DPI))
d = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_250)
W, H = int(210 / 25.4 * DPI), int(297 / 25.4 * DPI)
sheet = np.full((H, W), 255, np.uint8)

margin, gap_x, gap_y = 150, 200, 250
x = y = margin
for i in ids:
    if x + px > W - margin:                      # 줄바꿈
        x, y = margin, y + px + gap_y
    if y + px > H - margin:
        print(f"경고: ID {i} 이후는 A4 한 장에 안 들어감 — 나눠서 출력하세요")
        break
    sheet[y:y + px, x:x + px] = cv2.aruco.generateImageMarker(d, i, px)
    cv2.putText(sheet, f"ID {i} (R{i:02d})", (x, y + px + 60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, 0, 3)
    x += px + gap_x

out = "aruco_5x5_250_a4.png"
cv2.imwrite(out, sheet)
print(f"→ {out}  (A4, 마커 {mm:g}mm, DICT_5X5_250, '실제 크기'로 인쇄할 것)")
