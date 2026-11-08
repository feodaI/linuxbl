# Feodal 0.2 verification — 2026-11-08

## Artifacts

- ISO: `out/feodal-0.2.0-2-x86_64.iso`, 1,570,799,616 bytes.
- ISO SHA-256: `558f343f076b93a931ea5b2ee9077b15af060c6b8f82c6a5758ea842d266178f`.
- Package: `out/feodal-shell-0.2.0-2-any.pkg.tar.zst`.
- Package SHA-256: `609fa5d794cea0ddf19b849feac8751252e406f8de1b8b8983f77d3ea6ac2148`.

The package was built with makepkg as an unprivileged user on Arch, then installed
with pacman. All four packaged Python modules matched the checkout hashes.
The ISO was assembled with archiso 92-1 by upgrading the package in the retained
0.1 build root and regenerating its version/package lists, SquashFS and ISO.
The kernel/boot configuration and other installed packages were unchanged.
This was an incremental rebuild, not a second full package bootstrap.
`scripts/build-iso.sh` also supports building a fresh image using the new package
and now derives the output filename from its version. Generated artifacts are not
committed to Git. The previous dated 0.1 ISO remains separate.

## Automated checks

`./tests/run.sh` passed **30 tests**:

- 9 hardware tests: PCI/DRM detection, unbound devices, deduplication, missing
  commands, failed/timed-out nvidia-smi, and no false readiness with nouveau.
- 4 preference tests: atomic save/reload, owner-only file permissions, malformed
  values, XDG path handling, and explicit Steam launch command validation.
- 4 session tests: bounded activation environment, single D-Bus session,
  nonfatal activation-update failure, panel cleanup and WM exit status.
- 8 GTK/Openbox tests: original launcher/task behavior, control-center lifecycle,
  persistence, callbacks on the GTK thread, and Steam/NVIDIA launch guards.
- 4 live-readiness tests: pending/initializing/active keyring states, explicit
  failure, and a bounded wait. These cover a check that initially returned before
  the delayed live initialization job had started.
- 1 zram configuration test.

Python compilation, shell syntax, Openbox XML and whitespace checks also passed.
Mocked NVIDIA cases are not evidence of physical GPU compatibility.

## Booted ISO checks

Fresh QEMU guests: 2 vCPUs, 4096 MiB RAM, software emulation, **no data disk**.
The initial 0.2.0-1 image booted in BIOS and OVMF UEFI (Secure Boot disabled) and passed
`scripts/check-live-session.sh`: unprivileged shell, NetworkManager/DNS, disabled
competing network/SSH services, audio sockets, zram, and completed live keyring
initialization. The script waits for initial keyring setup rather than racing
pacman against it or weakening package signature checks.

In the BIOS guest, Super+I opened the control center. Its live hardware report
showed kernel 7.2.14-arch1-1, QEMU PCI GPU 1234:1111 / bochs-drm, and correctly
reported NVIDIA, prime-run and Steam unavailable. `feodal-hardware` also worked
as the unprivileged `feodal` user. The user activation environment contained
`DISPLAY=:0` and `XDG_CURRENT_DESKTOP=Feodal` after session startup.
Fresh screenshots were inspected from the booted 0.2 ISO. Release 2 fixes the
GPU dropdown's text/background contrast; its appearance was also verified in
an actual GTK/Xvfb session. Its package contains exactly the current module bytes.
The final 0.2.0-2 ISO was then booted again in a fresh BIOS QEMU guest with no
data disk. The updated live-session check passed (including completed keyring
initialization), and Super+I opened the current control center. Its screenshot
was freshly captured and inspected. UEFI proof applies to the earlier 0.2.0-1
image; release 2 changes only the shell's dropdown styling, not the boot chain.

## Limits

Steam itself is not bundled, and neither games nor NVIDIA/PRIME rendering were
run. The launch guards were tested with mocks, not a physical MX330. Legacy
580xx packages are not automatically installed. Physical Wi-Fi/audio, sleep,
Secure Boot, a lock screen and a Feodal disk installer remain unverified/absent.
The system remains an ephemeral live prototype, not a production installation.
