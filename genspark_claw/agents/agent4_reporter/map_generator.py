"""
Map Generator — OSM 타일 합성으로 베트남 지역 지도 생성
외부 API 키 불필요, curl + Pillow 사용
"""
import os, math, subprocess, io
from PIL import Image, ImageDraw, ImageFont

# 플랜별 지도 설정
PLAN_MAPS = {
    "VN-PWR-PDP8": {
        "title": "베트남 제8차 전력개발계획 (PDP8) — 주요 사업지역",
        "center": (16.0, 107.5), "zoom": 6,
        "markers": [
            (21.03, 105.83, "하노이\n(수도권 송전망)", "RED"),
            (10.82, 106.63, "호치민\n(남부 전력허브)", "RED"),
            (11.57, 108.97, "닌투안\n(해상풍력·원전)", "ORANGE"),
            (9.18,  105.15, "까마우\n(LNG 복합화력)", "BLUE"),
            (17.47, 106.59, "하띤\n(Vung Ang 화력)", "GRAY"),
            (20.84, 106.69, "하이퐁\n(북부 LNG)", "BLUE"),
        ],
    },
    "VN-ENV-IND-1894": {
        "title": "베트남 환경산업 발전 프로그램 (Decision 1894) — 주요 사업지역",
        "center": (16.0, 106.5), "zoom": 6,
        "markers": [
            (21.03, 105.83, "하노이\n(남선 매립지 현대화)", "RED"),
            (10.82, 106.63, "호치민\n(WTE 플랜트)", "RED"),
            (16.07, 108.21, "다낭\n(환경모니터링)", "ORANGE"),
            (10.97, 106.82, "빈즈엉\n(산업폐수처리)", "BLUE"),
            (10.04, 105.77, "껀터\n(메콩 폐수처리)", "GREEN"),
        ],
    },
    "VN-TRAN-2055": {
        "title": "베트남 국가 교통인프라 마스터플랜 2055 — 주요 사업지역",
        "center": (16.0, 107.5), "zoom": 6,
        "markers": [
            (21.03, 105.83, "하노이\n(Ring Road 4)", "RED"),
            (10.82, 106.63, "호치민\n(Ring Road 3)", "RED"),
            (10.66, 106.99, "롱탄\n(국제공항)", "ORANGE"),
            (20.84, 106.69, "하이퐁\n(락후옌 항만)", "BLUE"),
            (16.07, 108.21, "다낭\n(중부 허브)", "GREEN"),
        ],
    },
    "VN-GAS-PDP8": {
        "title": "베트남 LNG 가스 인프라 개발계획 — 주요 터미널·사업지역",
        "center": (12.0, 108.0), "zoom": 7,
        "markers": [
            (9.18,  105.15, "까마우\n(LNG 터미널 1MTPA)", "BLUE"),
            (10.62, 107.06, "티바이\n(LNG 터미널 운영중)", "GREEN"),
            (11.18, 108.82, "빈투안\n(손미 LNG 4,500MW)", "ORANGE"),
            (16.75, 107.19, "꽝찌\n(하이랑 LNG)", "BLUE"),
            (12.24, 109.19, "카인호아\n(냐짱 LNG)", "RED"),
        ],
    },
    "VN-EV-2030": {
        "title": "베트남 전기차·친환경 모빌리티 2030 — VinFast 생산거점 및 충전 인프라",
        "center": (19.0, 106.5), "zoom": 7,
        "markers": [
            (20.84, 106.69, "하이퐁\n(VinFast 공장 50만대)", "RED"),
            (21.03, 105.83, "하노이\n(전기버스 전환)", "ORANGE"),
            (10.82, 106.63, "호치민\n(EV 충전허브)", "ORANGE"),
            (21.09, 107.29, "꽝닌\n(EV 관광지)", "GREEN"),
            (10.97, 106.82, "빈즈엉\n(EV 부품 클러스터)", "BLUE"),
        ],
    },
    "VN-WW-2030": {
        "title": "베트남 국가 수처리 마스터플랜 2030 — 주요 WWTP 사업지역",
        "center": (18.0, 106.5), "zoom": 7,
        "markers": [
            (20.97, 105.80, "하노이\n(옌짜 WWTP 27만m³)", "RED"),
            (10.82, 106.63, "호치민\n(빈떤 WWTP 확장)", "RED"),
            (16.07, 108.21, "다낭\n(안돈 WWTP 신설)", "ORANGE"),
            (10.97, 106.82, "빈즈엉\n(산업폐수처리)", "BLUE"),
            (20.84, 106.69, "하이퐁\n(항만 폐수처리)", "GREEN"),
            (10.04, 105.77, "껀터\n(메콩 광역 하수망)", "BLUE"),
        ],
    },
    "VN-REN-NPP-2050": {
        "title": "베트남 원자력·신에너지 2050 — 원전 부지 및 주요 사업지역",
        "center": (13.0, 109.0), "zoom": 8,
        "markers": [
            (11.73, 108.87, "닌투안 1\n(원전 부지 재추진)", "RED"),
            (11.57, 108.90, "닌투안 2\n(원전 부지)", "RED"),
            (13.78, 109.22, "빈딘\n(SMR 후보지)", "ORANGE"),
            (15.12, 108.80, "꽝응아이\n(신에너지 클러스터)", "BLUE"),
        ],
    },
    "VN-SC-2030": {
        "title": "베트남 스마트시티 국가전략 2030 — 주요 스마트시티 개발지역",
        "center": (16.0, 107.0), "zoom": 6,
        "markers": [
            (21.03, 105.83, "하노이\n(UOCC 통합관제)", "RED"),
            (10.82, 106.63, "호치민\n(Thu Duc 스마트시티)", "RED"),
            (16.07, 108.21, "다낭\n(AI 교통관제)", "ORANGE"),
            (10.97, 106.82, "빈즈엉\n(스마트 산업도시)", "BLUE"),
            (21.09, 107.29, "꽝닌\n(스마트 관광)", "GREEN"),
        ],
    },
}

MARKER_COLORS = {
    "RED":    (220, 38, 38),
    "ORANGE": (234, 88, 12),
    "BLUE":   (29, 78, 216),
    "GREEN":  (5, 150, 105),
    "GRAY":   (100, 116, 139),
}

def deg2tile(lat, lon, zoom):
    n = 2 ** zoom
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1/math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return x, y

def tile2deg(x, y, zoom):
    n = 2 ** zoom
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2*y/n))))
    return lat, lon

def fetch_tile(x, y, zoom):
    url = f"https://tile.openstreetmap.org/{zoom}/{x}/{y}.png"
    result = subprocess.run(
        ["curl", "-s", "--max-time", "8", "-A", "VietnamInfraBot/1.0", "-o", "-", url],
        capture_output=True
    )
    if result.returncode == 0 and len(result.stdout) > 500:
        return Image.open(io.BytesIO(result.stdout)).convert("RGBA")
    return None

def generate_map(plan_id, output_path, tile_size=256):
    if plan_id not in PLAN_MAPS:
        return None
    cfg = PLAN_MAPS[plan_id]
    clat, clon = cfg["center"]
    zoom = cfg["zoom"]

    # 중심 타일
    cx, cy = deg2tile(clat, clon, zoom)

    # 3x3 타일 범위
    cols, rows = 4, 4
    x0 = cx - cols//2
    y0 = cy - rows//2

    # 타일 합성
    canvas = Image.new("RGBA", (cols*tile_size, rows*tile_size), (200,200,200,255))
    print(f"    타일 다운로드 중 ({cols*rows}개)...", end="", flush=True)
    ok = 0
    for dy in range(rows):
        for dx in range(cols):
            tile = fetch_tile(x0+dx, y0+dy, zoom)
            if tile:
                canvas.paste(tile, (dx*tile_size, dy*tile_size))
                ok += 1
    print(f" {ok}/{cols*rows} OK")

    draw = ImageDraw.Draw(canvas)

    # 마커 + 라벨 그리기
    for lat, lon, label, color_key in cfg["markers"]:
        col = MARKER_COLORS.get(color_key, MARKER_COLORS["RED"])
        # 픽셀 좌표 계산
        tx, ty = deg2tile(lat, lon, zoom)
        px = (tx - x0) * tile_size + tile_size//2
        py = (ty - y0) * tile_size + tile_size//2
        # 정확한 서브픽셀 위치
        frac_x = (lon - tile2deg(tx, ty, zoom)[1]) / (tile2deg(tx+1, ty, zoom)[1] - tile2deg(tx, ty, zoom)[1])
        frac_y = (tile2deg(tx, ty, zoom)[0] - lat) / (tile2deg(tx, ty, zoom)[0] - tile2deg(tx, ty+1, zoom)[0])
        px = int((tx - x0 + frac_x) * tile_size)
        py = int((ty - y0 + frac_y) * tile_size)

        if 0 <= px < cols*tile_size and 0 <= py < rows*tile_size:
            r = 10
            # 그림자
            draw.ellipse([px-r+2, py-r+2, px+r+2, py+r+2], fill=(0,0,0,80))
            # 마커 원
            draw.ellipse([px-r, py-r, px+r, py+r], fill=col+(230,), outline=(255,255,255,255), width=2)
            draw.ellipse([px-4, py-4, px+4, py+4], fill=(255,255,255,200))
            # 라벨 배경
            lines = label.split("\n")
            lw = max(len(l) for l in lines) * 7 + 8
            lh = len(lines) * 14 + 6
            lx, ly = px+12, py-lh//2
            draw.rectangle([lx-2, ly-2, lx+lw, ly+lh], fill=(255,255,255,200), outline=col+(200,), width=1)
            for i, line in enumerate(lines):
                draw.text((lx+2, ly+2+i*14), line, fill=col+(230,))

    # 제목 바
    title_h = 36
    title_bar = Image.new("RGBA", (cols*tile_size, title_h), (15,23,42,230))
    td = ImageDraw.Draw(title_bar)
    td.text((10, 8), cfg["title"], fill=(255,255,255,255))
    final = Image.new("RGBA", (cols*tile_size, rows*tile_size + title_h))
    final.paste(title_bar, (0, 0))
    final.paste(canvas, (0, title_h))

    # 출처 표시
    fd = ImageDraw.Draw(final)
    fd.rectangle([0, final.height-16, final.width, final.height], fill=(0,0,0,120))
    fd.text((4, final.height-14), "© OpenStreetMap contributors | Vietnam Infrastructure Intelligence Hub", fill=(200,200,200,255))

    # 저장
    final_rgb = final.convert("RGB")
    final_rgb.save(output_path, "PNG", quality=95)
    return output_path

def generate_all_maps(output_dir):
    os.makedirs(output_dir, exist_ok=True)
    results = {}
    for plan_id in PLAN_MAPS:
        out = os.path.join(output_dir, f"map_{plan_id}.png")
        print(f"  🗺️  {plan_id} 지도 생성 중...")
        try:
            path = generate_map(plan_id, out)
            if path:
                results[plan_id] = path
                print(f"    ✅ 저장: {os.path.basename(out)} ({os.path.getsize(out)//1024}KB)")
        except Exception as e:
            print(f"    ❌ 실패: {e}")
    return results

if __name__ == "__main__":
    maps = generate_all_maps("/home/work/claw/assets/maps")
    print(f"\n✅ 지도 {len(maps)}개 생성 완료")
