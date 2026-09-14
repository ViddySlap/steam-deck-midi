#!/bin/bash
# Mac-to-Windows transport. Remote scripts always run through PowerShell -File.
set -euo pipefail

SSH_OPTIONS=(-i "$HOME/.ssh/claude-mac-win-key" -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10)
HOST=ben@viddyslaptop.local
WORK='C:/Users/Ben/AppData/Local/Temp/sdwin'

die() { echo "$*" >&2; exit 64; }
quote() {
    # cmd.exe expands these even within quotes. Refuse instead of interpreting.
    case "$1" in
        *[\"\%\!\^\&\|\<\>]*|*$'\n'*|*$'\r'*) die 'Unsupported remote argument character' ;;
    esac
    local value=$1 trailing=''
    # Preserve trailing backslashes through Windows argv decoding.
    while [[ "$value" == *\\ ]]; do trailing="$trailing\\\\"; value=${value%\\}; done
    printf '"%s%s"' "$value" "$trailing"
}
tag_dir() {
    [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]] || die 'Invalid tag'
    REMOTE_DIR="$WORK/$1"
    ssh "${SSH_OPTIONS[@]}" "$HOST" "if not exist $(quote "$REMOTE_DIR") mkdir $(quote "$REMOTE_DIR")"
}
put_file() {
    [[ -f "$2" ]] || die "Local file not found: $2"
    local name
    name=$(basename "$2")
    [[ "$name" =~ ^[A-Za-z0-9._\ -]+$ ]] || die 'Unsupported upload filename'
    quote "$name" >/dev/null
    tag_dir "$1"
    REMOTE_FILE="$REMOTE_DIR/$name"
    scp "${SSH_OPTIONS[@]}" -- "$2" "$HOST:$REMOTE_FILE"
}

case "${1:-}" in
    run)
        [[ $# -ge 3 ]] || die 'Usage: win_rail.sh run <tag> <local.ps1> [args...]'
        [[ "$3" == *.ps1 ]] || die 'run requires a .ps1 file'
        # Validate every argument before making any remote change.
        for arg in "${@:4}"; do quote "$arg" >/dev/null; done
        put_file "$2" "$3"
        shift 3
        command_line="powershell -NoProfile -ExecutionPolicy Bypass -File $(quote "$REMOTE_FILE")"
        for arg in "$@"; do command_line="$command_line $(quote "$arg")"; done
        exec ssh "${SSH_OPTIONS[@]}" "$HOST" "$command_line"
        ;;
    put)
        [[ $# -eq 3 ]] || die 'Usage: win_rail.sh put <tag> <local>'
        put_file "$2" "$3"
        ;;
    get)
        [[ $# -eq 3 ]] || die 'Usage: win_rail.sh get <remote path> <local>'
        quote "$2" >/dev/null
        exec scp "${SSH_OPTIONS[@]}" -- "$HOST:${2//\\//}" "$3"
        ;;
    *) die 'Usage: win_rail.sh run|put|get ...' ;;
esac
