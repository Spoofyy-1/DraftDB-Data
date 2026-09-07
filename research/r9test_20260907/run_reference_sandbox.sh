#!/usr/bin/env bash
set -euo pipefail
stage=/home/ubuntu/nba/handoff/r9test
prediction_dir="$stage/results/reference"
[[ -f "$stage/code/reference_approval.json" ]] || exit 3
free_mib=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -n1)
[[ "$free_mib" =~ ^[0-9]+$ ]] && (( free_mib >= 20480 )) || { echo "Insufficient free GPU memory; require20GiB, leave I unchanged." >&2; exit 4; }
mkdir -p "$prediction_dir"
args=(--unshare-net --unshare-pid --unshare-ipc --unshare-uts --die-with-parent
      --dir /opt --chmod 0755 /opt --dir /etc --chmod 0755 /etc
      --dir /models --chmod 0755 /models --dir /models/hub --chmod 0755 /models/hub
      --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64
      --symlink usr/bin /bin --symlink usr/sbin /sbin
      --ro-bind /etc/alternatives /etc/alternatives --ro-bind /etc/ld.so.cache /etc/ld.so.cache
      --proc /proc --dev /dev --tmpfs /dev/shm --chmod 1777 /dev/shm
      --ro-bind /sys /sys --tmpfs /tmp --chmod 1777 /tmp
      --ro-bind /home/ubuntu/nba/.venv /opt/venv
      --ro-bind "$stage/code" /code
      --ro-bind /home/ubuntu/nba/handoff/r9h /h_reference
      --ro-bind /home/ubuntu/nba/handoff/r9g /reference
      --bind "$prediction_dir" /predictions
      --ro-bind /home/ubuntu/.cache/huggingface/hub/models--jingang--TabICL /models/hub/models--jingang--TabICL
      --setenv HF_HOME /models --setenv HF_HUB_OFFLINE 1 --setenv XDG_CACHE_HOME /tmp/cache
      --setenv OMP_NUM_THREADS 2 --setenv OPENBLAS_NUM_THREADS 2 --chdir /code)
for device in /dev/nvidia0 /dev/nvidiactl /dev/nvidia-uvm /dev/nvidia-uvm-tools; do
  if [[ -e "$device" ]]; then args+=(--dev-bind "$device" "$device"); fi
done
exec sudo -n bwrap "${args[@]}" /usr/bin/setpriv --reuid="$(id -u)" --regid="$(id -g)" --clear-groups --no-new-privs --bounding-set=-all /opt/venv/bin/python -u /code/reference_gate.py
