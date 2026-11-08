# Verification — 2026-11-08

## Artifact

- `out/feodal-2026.11.08-x86_64.iso` — 1,570,799,616 bytes.
- SHA-256: `624fbf8ab95898bf6c6b2a54ff318f15d50d4567cb3a5e322ccbc2b6471ead5a`.
- Built by `scripts/build-iso.sh` using archiso 92-1 in an isolated Arch VM.
- Standard kernel `linux 7.2.14.arch1-1`; shell package `feodal-shell 0.1.0-1`.
- The package/archive and ISO are generated outputs, not checked into Git.
- No builder authorized SSH key or generated RSA/Ed25519 SSH host private key was
  present at the checked image paths. SSH is masked in the live profile.

## Confirmed

- `./tests/run.sh`: 5 GTK/Openbox UI tests and 1 zram configuration test passed;
  Python compilation, shell syntax and Openbox XML parsing also passed.
- QEMU 8.2 software emulation, 2 vCPUs / 4096 MiB, no attached data disk:
  successful BIOS boot and separate OVMF UEFI boot with Secure Boot disabled.
- Both boots automatically started the custom panel and Openbox as `feodal`
  (UID 1000), not root.
- `scripts/check-live-session.sh` passed in **both** live VMs: NetworkManager and
  systemd-resolved active, DNS resolution working, competing network managers and
  SSH masked, PipeWire/PulseAudio sockets active, `/dev/zram0` enabled with zstd.
  With 4 GiB guest RAM its logical size was approximately 1.9 GiB.
- In the BIOS VM, Super+Space opened the launcher; searching for `xterm` and
  pressing Enter launched a real terminal and produced a task button.
- Fresh desktop, terminal and UEFI screenshots were captured from the booted ISO,
  not from the earlier standalone-shell prototype.

## Memory observation

In the same Ubuntu/Xvfb launcher smoke scenario, disabling the panel's unused
GDK GL context reduced process peak RSS from 268384 KiB to 79328 KiB (about
262 to 78 MiB). This is a process-local change: the original `GDK_GL` environment
is restored before launching other programs. These are shell-process measurements,
not total system RAM, target-laptop measurements, or FPS results.

## Still unverified / absent

- Physical MX330/Intel hybrid graphics, the proprietary 580xx driver, games/FPS,
  physical Wi-Fi/audio devices, laptop sleep and power management.
- Physical USB/UEFI boot and Secure Boot support.
- A Feodal installer, persistent storage setup, lock screen and production security
  configuration. Inherited Arch installation/rescue tools are not a validated
  Feodal installation workflow.
- PXE/netboot is intentionally excluded from the initramfs.

The ISO is an **ephemeral live prototype**. Test it in a VM first; it is not a
recommendation to replace an existing operating system or erase a disk.
