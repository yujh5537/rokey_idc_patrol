#!/usr/bin/env python3
"""
MAP-02 — 실측 도면 → 정적 지도(pgm/yaml) + racks.yaml 생성기
근거: 2026-09-09 도면 (350×560cm) + PM 확정 문답 (9/9)
좌표계: ROS 관례. 좌하단 원점, x 오른쪽 +, y 위쪽 +, 단위 m. 도면의 위→아래 값은 y = 5.60 - y_top.
재생성: python3 gen_static_map.py [--res 0.05]  → out/ 에 idc_testbed.pgm/.yaml, racks.yaml, preview.png
"""
import argparse, math, os, sys
import numpy as np

# ─────────── 실측 파라미터 (도면 기준, 단위 m) ───────────
BOARD_W, BOARD_H = 3.50, 5.60
CORRIDOR_W       = 0.80            # 복도 폭 (중간 벽 x 위치)
MID_WALL_OPEN    = (2.40, 3.20)    # 중간 벽 개구부 y 범위(ROS y) — 도면 위에서 240~320
WALL_T           = 0.005           # 벽 두께 0.5cm (렌더 시 최소 1셀)
RACK_W, RACK_D   = 0.21, 0.085     # 랙 폭(x) × 깊이(y)
RACKS_PER_ROW    = 7
RACK_X_RIGHT     = BOARD_W         # 랙 줄은 오른쪽 벽에 밀착
AISLE_OFFSET     = 0.615           # 랙 면 → 통로 중심선 거리
TRUNK_X          = 1.40            # 서버실 진입 트렁크(통로 입구) x
DOCK_X, DOCK_R   = 0.27, 0.15      # 도크 원 중심 x(벽에서 27cm), 반지름
DOCK_YAW         = math.pi         # 도킹 상태 로봇 전면 -x
MARGIN           = 0.50            # 지도 바깥 unknown 여백
ROBOT_R          = 0.171                       # Create 3 반경
MAX_INSPECT_X    = BOARD_W - ROBOT_R - 0.10    # 3.229 → col 1 점검 pose 클램프.
# 마진 10cm는 실물 벽면(3.495) 기준이 아니라 지도 렌더 벽면 기준으로 잡은 값 —
# res 0.05는 벽이 셀 경계에 맞춰 3.450까지 그려지므로 costmap 마진 = 3.450-3.229-0.171 = 5cm 확보.

# 랙 줄 정의: (도면 y_top 시작, 면 방향) — 면 방향 '-y'=아래(도면 기준 통로 쪽), '+y'=위
# 8줄, 위에서 아래로. ①단독 ②③등맞대기 ④⑤등맞대기 ⑥⑦등맞대기 ⑧단독
ROWS_TOP = [
    (0.000, 'down'), (1.315, 'up'), (1.400, 'down'),
    (2.715, 'up'),   (2.800, 'down'),
    (4.115, 'up'),   (4.200, 'down'),
    (5.515, 'up'),
]
# 통로(존): 도면 위→아래 Z1~Z4, 통로 중심선 y_top
ZONES_TOP = {'Z1': 0.70, 'Z2': 2.10, 'Z3': 3.50, 'Z4': 4.90}
ROW_ZONE  = ['Z1','Z1','Z2','Z2','Z3','Z3','Z4','Z4']   # 줄 ①~⑧이 면한 통로
ROBOT_ZONES = {'robot11': ['Z1','Z2'], 'robot5': ['Z3','Z4']}
DOCKS_TOP = {'robot11': 0.68, 'robot5': BOARD_H - 0.33}  # 도크 원 중심 y_top

# 순찰 순서 (PM 확정 9/9) — rack_id 문자열
PATROL = {
 'robot11': ['R07','R06','R05','R04','R03','R02','R01','R08','R09','R10','R11','R12','R13','R14',
             'R21','R20','R19','R18','R17','R16','R15','R22','R23','R24','R25','R26','R27','R28'],
 'robot5':  ['R56','R55','R54','R53','R52','R51','R50','R43','R44','R45','R46','R47','R48','R49',
             'R42','R41','R40','R39','R38','R37','R36','R29','R30','R31','R32','R33','R34','R35'],
}

def ros_y(y_top): return BOARD_H - y_top

def build_racks():
    racks = []
    rid = 1
    for row_i, (y0_top, face) in enumerate(ROWS_TOP):
        y_lo, y_hi = ros_y(y0_top + RACK_D), ros_y(y0_top)      # ROS y 범위
        zone = ROW_ZONE[row_i]
        aisle_y = ros_y(ZONES_TOP[zone])
        for k in range(RACKS_PER_ROW):                         # k=0 → 오른쪽 벽 쪽(R01, R08, ...)
            x_hi = RACK_X_RIGHT - k * RACK_W
            x_lo = x_hi - RACK_W
            cx, cy = (x_lo + x_hi) / 2, (y_lo + y_hi) / 2
            # 랙 면: 'down'(도면 아래)=ROS -y 방향으로 면함 → 로봇은 그 아래(작은 y)에서 +y(π/2)를 봄
            face_ros = '-y' if face == 'down' else '+y'
            face_y = y_lo if face_ros == '-y' else y_hi
            assert abs(abs(aisle_y - face_y) - AISLE_OFFSET) < 1e-6, (rid, aisle_y, face_y)
            # col 1은 랙이 오른쪽 벽에 붙어 있어 랙 x 중심에 로봇이 설 수 없음 → x 클램프 후
            # yaw를 랙 면 중심 지향으로 계산. 비클램프 시 atan2(±0.615, 0) = ±π/2 그대로.
            ix = min(cx, MAX_INSPECT_X)
            yaw = math.atan2(face_y - aisle_y, cx - ix)
            oblique = ix < cx
            racks.append(dict(
                rack_id=f'R{rid:02d}', aruco_id=rid, zone_id=zone, row=row_i + 1, col=k + 1,
                center=(round(cx, 4), round(cy, 4)), bbox=(round(x_lo,4), round(y_lo,4), round(x_hi,4), round(y_hi,4)),
                face=face_ros, inspect=(round(ix, 4), round(aisle_y, 4), round(yaw, 4)), oblique=oblique))
            rid += 1
    return racks

def render(racks, res):
    W = int(round((BOARD_W + 2*MARGIN) / res)); H = int(round((BOARD_H + 2*MARGIN) / res))
    img = np.full((H, W), 205, np.uint8)                     # unknown
    ox, oy = -MARGIN, -MARGIN                                # 지도 원점(좌하단, m)
    def cell(x, y):                                          # ROS m → 픽셀 (row 0 = 위)
        return int((x - ox) / res), H - 1 - int((y - oy) / res)
    def fill(x0, y0, x1, y1, val):                           # 반열림 [x0, x1) — 경계 셀 중복 방지
        c0 = int((x0 - ox) / res);            c1 = math.ceil((x1 - ox) / res) - 1
        r0 = H - math.ceil((y1 - oy) / res);  r1 = H - 1 - int((y0 - oy) / res)
        img[r0:max(r1, r0)+1, c0:max(c1, c0)+1] = val
    t = max(WALL_T, res)                                     # 최소 1셀
    fill(0, 0, BOARD_W, BOARD_H, 254)                        # 보드 내부 free
    fill(0, 0, BOARD_W, t, 0); fill(0, BOARD_H - t, BOARD_W, BOARD_H, 0)
    fill(0, 0, t, BOARD_H, 0); fill(BOARD_W - t, 0, BOARD_W, BOARD_H, 0)
    fill(CORRIDOR_W - t/2, 0, CORRIDOR_W + t/2, MID_WALL_OPEN[0], 0)   # 중간 벽 아래
    fill(CORRIDOR_W - t/2, MID_WALL_OPEN[1], CORRIDOR_W + t/2, BOARD_H, 0)  # 중간 벽 위
    for r in racks:
        x0, y0, x1, y1 = r['bbox']; fill(x0, y0, x1, y1, 0)
    return img, (ox, oy)

def write_pgm(path, img):
    with open(path, 'wb') as f:
        f.write(f'P5\n# MAP-02 static map — generated by gen_static_map.py\n{img.shape[1]} {img.shape[0]}\n255\n'.encode())
        f.write(img.tobytes())

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--res', type=float, default=0.05); ap.add_argument('--out', default='out')
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    racks = build_racks(); assert len(racks) == 56
    ids = {r['rack_id'] for r in racks}
    for rb, seq in PATROL.items():
        assert set(seq) <= ids and len(seq) == len(set(seq)) == 28, rb
        zs = {next(r for r in racks if r['rack_id']==s)['zone_id'] for s in seq}
        assert zs == set(ROBOT_ZONES[rb]), (rb, zs)
    img, (ox, oy) = render(racks, a.res)
    name = 'idc_testbed'
    write_pgm(f'{a.out}/{name}.pgm', img)
    with open(f'{a.out}/{name}.yaml', 'w') as f:
        f.write(f"""# MAP-02 정적 지도 — Nav2 map_server용. 실측 도면 350x560cm (2026-09-09)
image: {name}.pgm
mode: trinary
resolution: {a.res}
origin: [{ox:.3f}, {oy:.3f}, 0.0]   # 지도 좌하단(m). 보드 좌하단 = (0,0)
negate: 0
occupied_thresh: 0.65
free_thresh: 0.25
""")
    # racks.yaml
    L = ['# racks.yaml — MAP-02 산출물. 좌표계: 보드 좌하단 원점, x→, y↑, m, yaw rad (ROS map 프레임)',
         '# rack_id = "R" + aruco_id 2자리. row 1 = 도면 최상단 줄. col 1 = 오른쪽 벽 쪽.',
         '# face: 랙 도어가 향하는 방향. inspect_pose: 통로 중심선(랙 면에서 0.615m)에서 랙 도어 중심을 보는 pose.',
         f'# col 1은 벽 간섭으로 x={MAX_INSPECT_X:.3f} 클램프, yaw는 도어 중심 지향(≈74.9°/−74.9°) — oblique: true. AC는 "카메라 광축이 도어 중심 ±3°".',
         f'board: {{width: {BOARD_W}, height: {BOARD_H}, corridor_width: {CORRIDOR_W}, mid_wall_opening_y: [{MID_WALL_OPEN[0]}, {MID_WALL_OPEN[1]}], trunk_x: {TRUNK_X}}}',
         'zones:']
    for z, yt in ZONES_TOP.items():
        L.append(f'  {z}: {{aisle_y: {ros_y(yt):.3f}, entry_pose: {{x: {TRUNK_X}, y: {ros_y(yt):.3f}, yaw: 0.0}}}}')
    L.append('docks:')
    for rb, yt in DOCKS_TOP.items():
        L.append(f'  {rb}: {{x: {DOCK_X}, y: {ros_y(yt):.3f}, yaw: {DOCK_YAW:.4f}}}   # 원 중심, 로봇 전면 -x. AMCL 초기 pose로 사용')
    L.append('robot_zones:')
    for rb, zs in ROBOT_ZONES.items(): L.append(f'  {rb}: {zs}')
    L.append('racks:')
    for r in racks:
        cx, cy = r['center']; ix, iy, iyaw = r['inspect']
        L.append(f"  - {{rack_id: {r['rack_id']}, aruco_id: {r['aruco_id']}, zone_id: {r['zone_id']}, row: {r['row']}, col: {r['col']}, "
                 f"x: {cx:.4f}, y: {cy:.4f}, face: '{r['face']}', oblique: {str(r['oblique']).lower()}, "
                 f"inspect_pose: {{x: {ix:.4f}, y: {iy:.4f}, yaw: {iyaw:.4f}}}}}")
    L.append('patrol_routes:   # PM 확정 순서(9/9). 마지막 후 각자 docks[robot]으로 복귀')
    for rb, seq in PATROL.items(): L.append(f'  {rb}: [{", ".join(seq)}]')
    open(f'{a.out}/racks.yaml', 'w').write('\n'.join(L) + '\n')
    # preview
    try:
        from PIL import Image, ImageDraw
        s = 4; im = Image.fromarray(img).convert('RGB').resize((img.shape[1]*s, img.shape[0]*s), Image.NEAREST)
        d = ImageDraw.Draw(im); H = img.shape[0]
        def px(x, y): return ((x - ox)/a.res*s, (H - (y - oy)/a.res)*s)
        for rb, col in (('robot11', (255,190,0)), ('robot5', (200,120,255))):
            pts = [px(*DOCK_X and (DOCK_X, ros_y(DOCKS_TOP[rb])))]
            for rid in PATROL[rb]:
                r = next(r for r in racks if r['rack_id']==rid); pts.append(px(r['inspect'][0], r['inspect'][1]))
            d.line(pts, fill=col, width=2)
            for rid in PATROL[rb]:
                r = next(r for r in racks if r['rack_id']==rid); x,y = px(r['inspect'][0], r['inspect'][1]); d.ellipse((x-3,y-3,x+3,y+3), fill=col)
            dx, dy = px(DOCK_X, ros_y(DOCKS_TOP[rb])); rr = DOCK_R/a.res*s; d.ellipse((dx-rr,dy-rr,dx+rr,dy+rr), outline=(255,0,0), width=2)
        for r in racks:
            x,y = px(*r['center']); d.text((x-8,y-5), r['rack_id'][1:], fill=(0,90,255))
        im.save(f'{a.out}/preview.png')
    except ImportError: pass
    print(f'OK res={a.res} image={img.shape[1]}x{img.shape[0]} racks=56 out={a.out}/')

if __name__ == '__main__': main()
