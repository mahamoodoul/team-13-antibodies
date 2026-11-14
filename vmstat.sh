#!/usr/bin/env bash
# team-13 VM status widget — live view of the shared hackathon box.
#   ./vmstat.sh          refresh every 5s
#   ./vmstat.sh 15       refresh every 15s
#   ./vmstat.sh once     print once and exit (good for piping)
#
# Needs only the SSH key. Override the defaults with env vars:
#   VM_KEY=~/.ssh/team-13 VM_HOST=hackathon@1.2.3.4 ./vmstat.sh

set -uo pipefail

VM_KEY="${VM_KEY:-/Users/ansarulkabir/aixhackathon/keys/team-13}"
VM_HOST="${VM_HOST:-hackathon@89.169.97.216}"

ARG="${1:-5}"
if [[ "$ARG" == "once" ]]; then ONCE=1; INTERVAL=0; else ONCE=0; INTERVAL="$ARG"; fi

# Reuse one TCP connection across refreshes — without this every poll pays a
# fresh SSH handshake and the widget feels laggy.
CTL="${TMPDIR:-/tmp}/vmstat-team13-$(id -u).sock"
SSH_OPTS=(-i "$VM_KEY" -o BatchMode=yes -o ConnectTimeout=10
          -o ControlMaster=auto -o ControlPath="$CTL" -o ControlPersist=60)

cleanup() { ssh -O exit -o ControlPath="$CTL" "$VM_HOST" 2>/dev/null; tput cnorm 2>/dev/null; }
trap cleanup EXIT INT TERM

B=$'\033[1m'; DIM=$'\033[2m'; R=$'\033[0m'
RED=$'\033[31m'; GRN=$'\033[32m'; YEL=$'\033[33m'; CYN=$'\033[36m'

# One round trip collects everything; fields are tab-separated, sections are
# marked with @@NAME so the local side can split them apart.
remote_probe() {
  ssh "${SSH_OPTS[@]}" "$VM_HOST" 'bash -s' <<'REMOTE' 2>&1
echo "@@GPU"
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw \
           --format=csv,noheader,nounits 2>/dev/null || echo "n/a"
echo "@@PROC"
nvidia-smi --query-compute-apps=pid,used_memory,process_name \
           --format=csv,noheader,nounits 2>/dev/null
echo "@@DOCKER"
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}' 2>/dev/null | head -8
echo "@@DISK"
df -h / | awk 'NR==2{print $3"\t"$4"\t"$5}'
echo "@@DATA"
du -sh ~/data 2>/dev/null | cut -f1
find ~/data -type f 2>/dev/null | wc -l
echo "@@USERS"
for d in ansarul mahamodul rizve ruhit; do
  [ -d "$HOME/$d" ] || continue
  printf '%s\t%s\t%s\n' "$d" \
    "$(du -sh "$HOME/$d" 2>/dev/null | cut -f1)" \
    "$(find "$HOME/$d" -type f 2>/dev/null | wc -l | tr -d ' ')"
done
echo "@@LOAD"
uptime | sed 's/.*load average[s]*: //'
echo "@@WHO"
who | awk '{print $1}' | sort -u | tr '\n' ' '
echo
echo "@@END"
REMOTE
}

section() { awk -v s="@@$1" '$0==s{f=1;next} /^@@/{f=0} f' <<<"$2"; }

bar() { # bar <percent> <width>
  local p=${1%%.*} w=$2 filled
  [[ "$p" =~ ^[0-9]+$ ]] || { printf '%*s' "$w" ''; return; }
  filled=$(( p * w / 100 )); (( filled > w )) && filled=$w
  local c=$GRN; (( p >= 50 )) && c=$YEL; (( p >= 85 )) && c=$RED
  # Pad to width with spaces, then swap them for the glyph. Parameter
  # expansion handles multibyte characters, which `tr` does not.
  local on="" off=""
  (( filled > 0 ))      && { on=$(printf "%${filled}s" '');      on=${on// /█}; }
  (( w - filled > 0 ))  && { off=$(printf "%$((w-filled))s" ''); off=${off// /·}; }
  printf '%s%s%s%s%s' "$c" "$on" "$DIM" "$off" "$R"
}

render() {
  local raw; raw="$(remote_probe)"

  if ! grep -q '@@END' <<<"$raw"; then
    printf '%s  ✗ cannot reach %s%s\n\n%s%s%s\n' \
      "$RED" "$VM_HOST" "$R" "$DIM" "$(head -3 <<<"$raw")" "$R"
    return
  fi

  local gpu proc docker disk data users load who
  gpu="$(section GPU "$raw")";       proc="$(section PROC "$raw")"
  docker="$(section DOCKER "$raw")"; disk="$(section DISK "$raw")"
  data="$(section DATA "$raw")";     users="$(section USERS "$raw")"
  load="$(section LOAD "$raw")";     who="$(section WHO "$raw")"

  IFS=',' read -r util memu memt temp pwr <<<"$gpu"
  util="${util// /}"; memu="${memu// /}"; memt="${memt// /}"
  temp="${temp// /}"; pwr="${pwr// /}"
  local mempct=0; [[ "$memt" =~ ^[0-9]+$ ]] && (( memt > 0 )) && mempct=$(( memu * 100 / memt ))

  printf '%s┌─ team-13 VM %s%s%s\n' "$B" "$DIM" "$VM_HOST  ·  $(date '+%H:%M:%S')" "$R"
  printf '%s│%s\n' "$B" "$R"

  # --- GPU ---
  printf '%s│%s  %sH100 80GB%s\n' "$B" "$R" "$CYN" "$R"
  printf '%s│%s    compute  %s %3s%%   %s%s°C  %sW%s\n' \
    "$B" "$R" "$(bar "${util:-0}" 24)" "${util:-?}" "$DIM" "${temp:-?}" "${pwr%%.*}" "$R"
  printf '%s│%s    memory   %s %3s%%   %s%s / %s MiB%s\n' \
    "$B" "$R" "$(bar "$mempct" 24)" "$mempct" "$DIM" "${memu:-?}" "${memt:-?}" "$R"

  if [[ -n "${proc// /}" ]]; then
    printf '%s│%s    %srunning:%s\n' "$B" "$R" "$GRN" "$R"
    while IFS=',' read -r pid mem name; do
      [[ -z "${pid// /}" ]] && continue
      printf '%s│%s      %s pid %s · %s MiB · %s%s\n' \
        "$B" "$R" "$DIM" "${pid// /}" "${mem// /}" "$(basename "${name// /}")" "$R"
    done <<<"$proc"
  else
    printf '%s│%s    %s(idle — no compute processes)%s\n' "$B" "$R" "$DIM" "$R"
  fi
  printf '%s│%s\n' "$B" "$R"

  # --- containers ---
  if [[ -n "${docker// /}" ]]; then
    printf '%s│%s  %sContainers%s\n' "$B" "$R" "$CYN" "$R"
    while IFS=$'\t' read -r name status image; do
      [[ -z "$name" ]] && continue
      printf '%s│%s    %s%-18s%s %s %s%s%s\n' "$B" "$R" "$GRN" "$name" "$R" \
        "$status" "$DIM" "${image##*:}" "$R"
    done <<<"$docker"
    printf '%s│%s\n' "$B" "$R"
  fi

  # --- work on disk ---
  printf '%s│%s  %sWork%s\n' "$B" "$R" "$CYN" "$R"
  local dsize dcount
  dsize="$(sed -n 1p <<<"$data")"; dcount="$(sed -n 2p <<<"$data")"
  printf '%s│%s    %-12s %6s  %s%s files%s\n' "$B" "$R" "~/data" \
    "${dsize:-0}" "$DIM" "${dcount:-0}" "$R"
  while IFS=$'\t' read -r u sz n; do
    [[ -z "$u" ]] && continue
    local c="$DIM"; [[ "${n:-0}" -gt 0 ]] && c="$R"
    printf '%s│%s    %s%-12s %6s  %s%s files%s\n' "$B" "$R" "$c" "~/$u" "$sz" "$DIM" "$n" "$R"
  done <<<"$users"
  printf '%s│%s\n' "$B" "$R"

  # --- box ---
  local used avail pct
  IFS=$'\t' read -r used avail pct <<<"$disk"
  printf '%s│%s  %sBox%s      disk %s used · %s free (%s)   load%s%s%s\n' \
    "$B" "$R" "$CYN" "$R" "$used" "$avail" "$pct" "$DIM" " $load" "$R"
  printf '%s│%s           logged in: %s%s%s\n' "$B" "$R" "$DIM" "${who:-none}" "$R"
  printf '%s└─%s\n' "$B" "$R"
}

if (( ONCE )); then
  render
else
  tput civis 2>/dev/null
  while true; do
    out="$(render)"
    clear
    printf '%s\n' "$out"
    printf '%s  refreshing every %ss — ctrl-c to stop%s\n' "$DIM" "$INTERVAL" "$R"
    sleep "$INTERVAL"
  done
fi
