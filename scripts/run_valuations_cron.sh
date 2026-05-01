#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────
# Funda valuation cron wrapper
#
# Runs `python -m funda.run_valuations` under flock so overlapping
# ticks can never start a second Walter browser. Logs are appended
# and rotated (kept under 5 MB).
#
# Install (every 15 min):
#   crontab -e
#   */15 * * * * /home/soohanur/Desktop/Funda/scripts/run_valuations_cron.sh
#
# Tunables via env (set in crontab line or a wrapper):
#   FUNDA_HOME      project root (default: /home/soohanur/Desktop/Funda)
#   FUNDA_PYTHON    python binary (default: python3)
#   VAL_LIMIT       max rows per run (default: 20)
#   VAL_LOG         log file (default: $FUNDA_HOME/funda/logs/valuations_cron.log)
# ─────────────────────────────────────────────────────────────────
set -u

FUNDA_HOME="${FUNDA_HOME:-/home/soohanur/Desktop/Funda}"
FUNDA_PYTHON="${FUNDA_PYTHON:-python3}"
VAL_LIMIT="${VAL_LIMIT:-20}"
VAL_LOG="${VAL_LOG:-$FUNDA_HOME/funda/logs/valuations_cron.log}"
LOCK_FILE="${LOCK_FILE:-/tmp/funda_run_valuations.lock}"
MAX_LOG_BYTES="${MAX_LOG_BYTES:-5242880}"   # 5 MB

mkdir -p "$(dirname "$VAL_LOG")"

# Cheap log rotation — keep one .1 backup
if [ -f "$VAL_LOG" ]; then
    size=$(stat -c%s "$VAL_LOG" 2>/dev/null || echo 0)
    if [ "$size" -gt "$MAX_LOG_BYTES" ]; then
        mv -f "$VAL_LOG" "$VAL_LOG.1"
    fi
fi

cd "$FUNDA_HOME" || { echo "[$(date)] FUNDA_HOME not found: $FUNDA_HOME" >> "$VAL_LOG"; exit 2; }

{
    echo "──────────────────────────────────────────────────────"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] cron tick (limit=$VAL_LIMIT)"
} >> "$VAL_LOG"

# -n = non-blocking. If a previous run is still going, exit 0 quietly.
flock -n "$LOCK_FILE" "$FUNDA_PYTHON" -m funda.run_valuations --limit "$VAL_LIMIT" \
    >> "$VAL_LOG" 2>&1
rc=$?

if [ $rc -eq 0 ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] done OK" >> "$VAL_LOG"
elif [ $rc -eq 1 ]; then
    # flock will exit with the command's exit code; 1 from python = error
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] run failed (rc=1)" >> "$VAL_LOG"
elif [ $rc -eq 75 ]; then
    # Reserved for "another instance running" if we ever flip to non-zero
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] previous run still active — skipping" >> "$VAL_LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] exited rc=$rc" >> "$VAL_LOG"
fi

exit $rc
