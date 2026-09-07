#!/usr/bin/env bash
set -euo pipefail
root=/home/ubuntu/nba/handoff/r9m
task="$1"
mode="${2:-fit}"
[[ "$task" =~ ^[a-z0-9_]+_y201[234]$ ]]
[[ "$mode" == fit || "$mode" == preflight ]]
out="$root/results/jobs/$task"
mkdir -p "$out"
args=(--unshare-net --unshare-pid --unshare-ipc --unshare-uts --die-with-parent
      --dir /opt --chmod 0755 /opt --dir /etc --chmod 0755 /etc
      --dir /models --chmod 0755 /models --dir /models/hub --chmod 0755 /models/hub
      --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64
      --symlink usr/bin /bin --symlink usr/sbin /sbin
      --ro-bind /etc/alternatives /etc/alternatives --ro-bind /etc/ld.so.cache /etc/ld.so.cache
      --proc /proc --dev /dev --tmpfs /dev/shm --chmod 1777 /dev/shm
      --ro-bind /sys /sys --tmpfs /tmp --chmod 1777 /tmp
      --ro-bind /home/ubuntu/nba/.venv /opt/venv
      --ro-bind "$root/code" /code
      --ro-bind "$root/inputs/$task" /input
      --bind "$out" /output
      --ro-bind /home/ubuntu/.cache/huggingface/hub/models--jingang--TabICL /models/hub/models--jingang--TabICL
      --setenv HF_HOME /models --setenv HF_HUB_OFFLINE 1 --setenv XDG_CACHE_HOME /tmp/cache
      --setenv OMP_NUM_THREADS 2 --setenv OPENBLAS_NUM_THREADS 2
      --chdir /code)
for dev in /dev/nvidia0 /dev/nvidiactl /dev/nvidia-uvm /dev/nvidia-uvm-tools; do
  if [[ -e "$dev" ]]; then args+=(--dev-bind "$dev" "$dev"); fi
done
extra=()
if [[ "$mode" == preflight ]]; then extra+=(--preflight-only); output=/output/preflight.json
else output=/output/result.json; fi
exec sudo -n bwrap "${args[@]}" /usr/bin/setpriv --reuid="$(id -u)" --regid="$(id -g)" --clear-groups --no-new-privs --bounding-set=-all \
     /opt/venv/bin/python -u /code/worker.py --input-dir /input --output "$output" "${extra[@]}"
