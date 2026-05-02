#!/bin/bash
# Vietnam Infrastructure News Pipeline — 실행 래퍼
# tmux 세션에서 실행되도록 보장 (gsk CLI TTY 요구사항 해결)
# 사용법: bash run_pipeline.sh [--test]

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/outputs/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/pipeline_$(date +%Y%m%d_%H%M%S).log"
SESSION="vn_pipeline_$$"

echo "========================================"
echo "Vietnam News Pipeline 시작: $(date '+%Y-%m-%d %H:%M:%S KST')"
echo "로그: $LOG_FILE"
echo "========================================"

# tmux가 없으면 직접 실행 (폴백)
if ! command -v tmux &>/dev/null; then
  cd "$SCRIPT_DIR"
  source venv/bin/activate
  python main_complete.py 2>&1 | tee "$LOG_FILE"
  exit $?
fi

# 현재 이미 tmux 안에 있으면 직접 실행
if [ -n "$TMUX" ]; then
  cd "$SCRIPT_DIR"
  source venv/bin/activate
  python main_complete.py 2>&1 | tee "$LOG_FILE"
  exit $?
fi

# tmux 세션 생성 후 실행, 완료 대기
tmux new-session -d -s "$SESSION" -x 220 -y 50
tmux send-keys -t "$SESSION" "
cd $SCRIPT_DIR && source venv/bin/activate &&
python main_complete.py 2>&1 | tee $LOG_FILE
echo \$? > $LOG_DIR/exit_code.txt
echo PIPELINE_DONE >> $LOG_FILE
" Enter

echo "tmux 세션 '$SESSION' 에서 실행 중..."
echo "(실시간 확인: tmux attach -t $SESSION)"
echo ""

# 완료 대기 (최대 90분)
TIMEOUT=5400
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
  if grep -q "PIPELINE_DONE" "$LOG_FILE" 2>/dev/null; then
    break
  fi
  sleep 10
  ELAPSED=$((ELAPSED + 10))
  # 진행 상황 출력 (1분마다)
  if [ $((ELAPSED % 60)) -eq 0 ]; then
    LAST=$(tail -3 "$LOG_FILE" 2>/dev/null | tr '\n' ' ')
    echo "[${ELAPSED}s] $LAST"
  fi
done

EXIT_CODE=$(cat "$LOG_DIR/exit_code.txt" 2>/dev/null || echo "1")
tmux kill-session -t "$SESSION" 2>/dev/null || true

if [ "$EXIT_CODE" = "0" ]; then
  echo ""
  echo "✅ 파이프라인 완료 (exit 0)"
else
  echo ""
  echo "❌ 파이프라인 실패 (exit $EXIT_CODE)"
  echo "로그 확인: $LOG_FILE"
  exit 1
fi
