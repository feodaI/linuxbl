# Feodal 0.6 verification — 2026-11-10

## Automated checks

`bash tests/run.sh` passes: 97 tests, Python compilation, shell syntax and XML
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

Current-image build and clean-disk boot/install results are recorded below
once complete. Previous 0.5 image boot evidence is not evidence for 0.6.

## Boundaries

No physical i3-1115G4/MX330 machine is attached. Wi-Fi, physical audio, battery,
brightness, suspend/resume, lid behavior, external monitors, real USB media,
NVIDIA rendering and game FPS remain hardware tests. No game-account login,
Dota 2 match or GTA V gameplay is claimed. GTA Online is not supported on Linux
through BattlEye. Secure Boot, disk encryption and dual boot are not provided.
