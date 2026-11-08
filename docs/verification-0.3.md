# Feodal 0.3 verification — 2026-11-08

## Artifacts and build

- ISO: `out/feodal-0.3.0-1-x86_64.iso`, 1,808,957,440 bytes.
- ISO SHA-256: `cf8db998cf155f27a9bec4e30c6b5777cf777fad62c89940cab5bd4e3a43ef89`.
- Shell package: `out/feodal-shell-0.3.0-1-any.pkg.tar.zst`.
- Package SHA-256: `40a55f1cbe8795c7e27445d51f375ef8bd39b9be78e80fe74d067c89192138a7`.

The shell was packaged with makepkg as the unprivileged `feodal` user in Arch.
Packaged module hashes and the local homepage hash matched the checkout. Official
Arch desktop packages were installed with pacman and signature verification into
the retained build root; archiso 92-1 regenerated the package list, SquashFS and
ISO. This was an incremental rebuild of the existing image, not a full second
bootstrap. Fresh builds use `scripts/build-iso.sh` and `iso/packages.desktop`.
The previous kernel and boot chain were retained. No builder authorized SSH key
or Ed25519 SSH host key was present in the image at the checked paths.

## Automated checks

`./tests/run.sh`: **35 tests passed**, including four new desktop-default tests
and a panel Firefox-button test, in addition to the existing hardware, GTK,
session, preferences, live-readiness and zram coverage. Python compilation, shell
syntax, Openbox XML and whitespace checks also passed.

The tests cover the local/unlocked homepage policy, the first-run-tour policy,
correct upstream desktop IDs, Firefox shortcut, ISO package selection, and a
start page without JavaScript or automatic external-resource loads. Firefox
itself retains its normal upstream network behavior; this is not a claim that
all browser background network requests are disabled.

## Booted ISO and application checks

This exact ISO booted in fresh QEMU BIOS and OVMF UEFI guests, 2 vCPUs and 4096 MiB
RAM, no attached data disk, software emulation, Secure Boot disabled. Both passed
`scripts/check-live-session.sh`: unprivileged desktop, network/DNS, service masks,
audio sockets, zram, and completed pacman keyring initialization.

In the BIOS guest:

- **Super+B** opened official Firefox as the normal user with the local Feodal
  homepage. Its appearance was captured and inspected from the booted ISO.
- Typing `archlinux` in the homepage search field and pressing Enter navigated
  to DuckDuckGo over HTTPS and displayed search results; a fresh screenshot was
  inspected. No Firefox sandbox-disable options or environment variables were used.
- `xdg-mime query default` in the Feodal session returned `firefox.desktop` for
  HTTPS, `org.xfce.mousepad.desktop` for plain text, `xarchiver.desktop` for ZIP,
  and `mpv.desktop` for MP4.
- Mousepad, Xarchiver and mpv were launched as UID 1000 and their processes
  confirmed. This is a launch check, not full codec/archive-format coverage or
  evidence of physical audio output.
- Installed versions: Firefox and Ukrainian language pack `159.0.1-1`, Mousepad
  `0.7.0-1`, Xarchiver `0.5.4.27-1`, mpv `1:0.41.0-7`.

## Limits

The system remains an ephemeral live prototype. Browser profile, downloads and
user settings are lost after reboot unless saved to separate persistent storage.
There is no Feodal installer or screen locker. Physical MX330/NVIDIA legacy
580xx, games/FPS, laptop sleep and physical Wi-Fi/audio remain unverified.
Firefox is the official Arch package, not a separately maintained Feodal fork.
