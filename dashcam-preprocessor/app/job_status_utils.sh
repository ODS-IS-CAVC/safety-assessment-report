#!/bin/bash

# ローカルJSONから前回の処理ステップを読み込む関数
load_last_step() {
    if [ -f "$STATUS_FILE" ]; then
        last_step=$(jq -r '.last_step' "$STATUS_FILE")
    else
        last_step="NOT_STARTED"
    fi
}

# ローカルJSONにステップを保存する関数
save_last_step() {
    local step=$1
    echo "{\"last_step\": \"$step\"}" > "$STATUS_FILE"
    last_step=$step
}
