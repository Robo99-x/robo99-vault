#!/bin/bash
# kill_telegram_zombies.sh
# Claude Code 시작 전 좀비 텔레그램 MCP 프로세스 정리
# 사용법: 새 세션 시작 전 실행, 또는 메시지 미도달 시 실행

KILLED=0

# 텔레그램 MCP 플러그인 좀비 프로세스 탐지 및 종료
while IFS= read -r line; do
    PID=$(echo "$line" | awk '{print $2}')
    CURRENT_PID=$$
    CLAUDE_PID=$(pgrep -f "claude --channels plugin:telegram" | head -1)

    # 현재 Claude 세션의 텔레그램 플러그인은 제외
    if [ "$PID" != "$CURRENT_PID" ] && [ "$PID" != "$CLAUDE_PID" ]; then
        # 부모 프로세스 확인 — 현재 Claude 세션 하위가 아니면 좀비
        PPID=$(ps -p "$PID" -o ppid= 2>/dev/null | tr -d ' ')
        if [ "$PPID" != "$CLAUDE_PID" ]; then
            echo "[kill] 좀비 프로세스 종료: PID $PID"
            kill -9 "$PID" 2>/dev/null && KILLED=$((KILLED + 1))
        fi
    fi
done < <(pgrep -a -f "external_plugins/telegram" 2>/dev/null | grep -v "^$$")

if [ "$KILLED" -eq 0 ]; then
    echo "[ok] 좀비 프로세스 없음"
else
    echo "[done] $KILLED 개 좀비 프로세스 종료 완료"
fi
