#!/usr/bin/env bash
set -euo pipefail
root=/home/ubuntu/nba/handoff/r8perf
args=(--unshare-net --unshare-pid --unshare-ipc --unshare-uts --die-with-parent
      --dir /opt --chmod 0755 /opt --dir /etc --chmod 0755 /etc
      --dir /models --chmod 0755 /models --dir /models/hub --chmod 0755 /models/hub
      --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64
      --symlink usr/bin /bin --symlink usr/sbin /sbin
      --ro-bind /etc/alternatives /etc/alternatives --ro-bind /etc/ld.so.cache /etc/ld.so.cache --proc /proc --dev /dev --tmpfs /dev/shm --chmod 1777 /dev/shm
      --ro-bind /sys /sys --tmpfs /tmp --chmod 1777 /tmp
      --ro-bind /home/ubuntu/nba/.venv /opt/venv
      --ro-bind "$root" /workspace
      --bind "$root/results" /workspace/results
      --ro-bind /home/ubuntu/.cache/huggingface/hub/models--jingang--TabICL /models/hub/models--jingang--TabICL
      --setenv HF_HOME /models --setenv HF_HUB_OFFLINE 1 --setenv XDG_CACHE_HOME /tmp/cache
      --setenv R8_SANDBOX 1 --setenv OMP_NUM_THREADS 6 --setenv OPENBLAS_NUM_THREADS 6
      --chdir /workspace)
for dev in /dev/nvidia0 /dev/nvidiactl /dev/nvidia-uvm /dev/nvidia-uvm-tools; do
  if [[ -e "$dev" ]]; then args+=(--dev-bind "$dev" "$dev"); fi
done
exec sudo -n bwrap "${args[@]}" /usr/bin/setpriv --reuid="$(id -u)" --regid="$(id -g)" --clear-groups --no-new-privs --bounding-set=-all /opt/venv/bin/python -u /workspace/weight_reuse.py "$@"
