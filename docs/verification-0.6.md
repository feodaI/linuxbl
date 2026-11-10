# Feodal 0.6 verification — 2026-11-10

## Automated checks

`bash tests/run.sh` passes: 98 tests, Python compilation, shell syntax and XML
parsing. Includes live-disk/mounted-disk protection, revalidation before erase,
mount-loss/unmount failure, password handling, replacing the live `feodal`
account, fixed package-hook ordering, GUI wizard flow, screen-lock integration,
Steam offload without `nvidia-prime`, and the Intel/multilib image selection.
`git diff --check` passes.

GTK settings and installer welcome/apps pages were also opened and captured in
fresh Xvfb sessions. These are appearance/interaction checks, not installation
proof or GPU benchmarks.

## Google Antigravity

Antigravity 2.29.1 displayed its welcome/sign-in UI in the existing installed
QEMU VM with `-cpu max` and `--disable-gpu`. Confirmed a normal mapped window
using X11 properties and inspected the fresh screenshot. The release launcher
uses that software-rendering flag; the Chromium sandbox is not disabled.
Google sign-in, AI requests and physical GPU rendering were not tested.

## Image / installation

The Arch builder used the retained archiso work tree and signed official
packages from the matching 2026-11-08 archive snapshot. The final filesystem was
recompressed natively with zstd level 19, keeping the ISO below GitHub's 2 GiB
asset limit. A discovered overlay ownership problem was corrected: root and
system overlay paths are owned by root, not the checkout/build user. The build
script now copies overlays without preserving ownership and explicitly sets
the SquashFS root UID/GID to zero.

Canonical tar streams before/after recompression, allowing only that ownership
correction, have identical SHA-256:
`0708b5cd2e234c81945fde3adee02daa89925f0be1e63ea26e41cd49a3689c8a`.
A separate complete metadata scan confirmed no UID/GID 1000 owners under /etc
or /usr and a root-owned 0755 SquashFS root. The SquashFS SHA-512 file was
regenerated; xorriso replayed the BIOS/UEFI boot configuration.

Final ISO: `feodal-0.6.0-1-x86_64.iso`, 2,067,726,336 bytes.
SHA-256: `f48c2ff0991beb43b9e31dae3760b5f6fa3158abcdfb5b974818af2e54774692`.
Shell package SHA-256:
`d7bc082faff0dec5a9c002c5b9c643a476829be352c4926d19eceecee25ac912`.

The final ISO reached the desktop in UEFI QEMU (TCG, CPU max, 3 GiB RAM),
with an empty 40 GiB virtual target disk attached. Actual GTK wizard automation
was launched from the live user's terminal and used the installed pkexec
backend, not a fake backend. The wizard completed with `warnings: []`.
It erased/partitioned/formatted only that disposable virtual disk, copied the
system, replaced the live `feodal` account with a password-protected `feodal`
account, generated both initramfs images, installed BIOS and UEFI GRUB, downloaded
and checksum-verified Antigravity, and successfully unmounted the target.
The earlier unreadable `/boot/vmlinuz-linux` error is absent from the install
log. The final initramfs images were about 18 MiB (default) and 224 MiB (fallback).
This software-emulated installation took about 33 minutes; it is not a timing
claim for physical hardware.

A non-blocking live optical-media diagnostic is present: systemd-loop attempts
to dissect /dev/sr0 and reports "No suitable partitions found". The Archiso
SquashFS mount, desktop and installer are operational; this is not reported as
a clean systemd --failed result. Previous 0.5 boot evidence is not 0.6 proof.

## Boundaries

No physical i3-1115G4/MX330 machine is attached. Wi-Fi, physical audio, battery,
brightness, suspend/resume, lid behavior, external monitors, real USB media,
NVIDIA rendering and game FPS remain hardware tests. No game-account login,
Dota 2 match or GTA V gameplay is claimed. GTA Online is not supported on Linux
through BattlEye. Secure Boot, disk encryption and dual boot are not provided.
