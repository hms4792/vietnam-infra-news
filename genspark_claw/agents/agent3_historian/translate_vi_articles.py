"""
베트남어 기사 gsk 번역 스크립트
- history_db.json의 베트남어 기사에 summary_ko / summary_en 추가
- gsk summarize 사용 (URL 또는 content 기반)
"""
import json, subprocess, sys, re, time
from pathlib import Path

DB_PATH = "/home/work/claw/config/history_db.json"
VI_CHARS = ['ă','ơ','ư','đ','ấ','ề','ộ','ừ','ạ','ọ','ổ','ị','ế','ỉ','ặ','ứ']

def is_vi(text):
    return any(c in (text or '') for c in VI_CHARS)

def gsk_translate(url, content, title):
    """gsk summarize로 번역 시도. URL 우선, 실패시 content 사용."""
    prompt = (
        "이 기사를 읽고 다음 두 가지를 제공해주세요:\n"
        "1. 한국어 요약 (3-4문장, 핵심 내용과 수치 포함)\n"
        "2. English summary (2-3 sentences)\n\n"
        "형식:\n"
        "KO: [한국어 요약]\n"
        "EN: [English summary]"
    )
    
    # URL로 시도
    if url:
        try:
            result = subprocess.run(
                ["gsk", "summarize", url, "--question", prompt],
                capture_output=True, text=True, timeout=45
            )
            if result.returncode == 0 and result.stdout.strip():
                return parse_translation(result.stdout)
        except Exception:
            pass
    
    # content가 있으면 직접 번역
    if content:
        text_input = f"제목: {title}\n\n내용: {content[:1000]}"
        try:
            result = subprocess.run(
                ["gsk", "summarize", "-", "--question", prompt],
                input=text_input, capture_output=True, text=True, timeout=45
            )
            if result.returncode == 0 and result.stdout.strip():
                return parse_translation(result.stdout)
        except Exception:
            pass
    
    return None, None

def parse_translation(text):
    ko, en = None, None
    lines = text.strip().split('\n')
    for line in lines:
        if line.startswith('KO:'):
            ko = line[3:].strip()
        elif line.startswith('EN:'):
            en = line[3:].strip()
    # 파싱 실패시 전체 텍스트에서 추출
    if not ko:
        m = re.search(r'(?:KO:|한국어)\s*(.+?)(?:EN:|English|$)', text, re.DOTALL)
        if m: ko = m.group(1).strip()[:400]
    if not en:
        m = re.search(r'(?:EN:|English)\s*(.+?)$', text, re.DOTALL)
        if m: en = m.group(1).strip()[:400]
    return ko, en

def main():
    with open(DB_PATH, encoding='utf-8') as f:
        db = json.load(f)
    
    articles = db['articles']
    
    # 번역 대상: 베트남어 제목 + 2026년 + summary 없음
    targets = {
        uid: art for uid, art in articles.items()
        if is_vi(art.get('title',''))
        and re.search(r'2026', str(art.get('published_date','')))
        and not art.get('summary_ko')
    }
    
    print(f"번역 대상: {len(targets)}건")
    
    ok = 0
    fail = 0
    for i, (uid, art) in enumerate(targets.items(), 1):
        title = art.get('title','')
        url = art.get('url','')
        content = art.get('content','')
        
        print(f"[{i:02d}/{len(targets)}] {title[:60]}...", end=' ', flush=True)
        
        ko, en = gsk_translate(url, content, title)
        
        if ko:
            art['summary_ko'] = ko
            art['summary_en'] = en or ''
            ok += 1
            print(f"✅")
        else:
            # 최소한 제목 번역
            art['summary_ko'] = f"[번역 필요] {title}"
            fail += 1
            print(f"❌")
        
        # 10건마다 저장
        if i % 10 == 0:
            with open(DB_PATH, 'w', encoding='utf-8') as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            print(f"  💾 중간 저장 ({i}건 처리)")
        
        time.sleep(1)  # rate limit
    
    # 최종 저장
    with open(DB_PATH, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 번역 완료: 성공 {ok}건 / 실패 {fail}건")

if __name__ == "__main__":
    main()
