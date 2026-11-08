#!/bin/sh
set -eu
if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    printf 'Usage: %s image.iso [memory-MiB]\n' "$0" >&2
    exit 2
fi
command -v qemu-system-x86_64 >/dev/null
iso=$(realpath -e -- "$1")
[ -f "$iso" ] || exit 1
memory=${2:-4096}
case "$memory" in ''|*[!0-9]*) printf '%s\n' 'Memory must be a number of MiB.' >&2; exit 2 ;; esac
[ "$memory" -ge 2048 ] || { printf '%s\n' 'Use at least 2048 MiB.' >&2; exit 2; }
# No host disk is passed through. TCG also works without /dev/kvm.
exec qemu-system-x86_64 -accel tcg -m "$memory" -smp 2 -boot d \
    -cdrom "$iso" -nic user,model=virtio-net-pci -vga std -no-reboot
