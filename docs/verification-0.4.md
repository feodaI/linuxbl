# Feodal 0.4 verification — 2026-11-08

## Artifacts

- Final ISO: `out/feodal-0.4.0-2-x86_64.iso`, 1,819,082,752 bytes.
- ISO SHA-256: `c1a6dc6e3642a80a59de4b57db2100e1ac59b97a4a31b40af75ee3bd03bf7e5c`.
- Package: `out/feodal-shell-0.4.0-2-any.pkg.tar.zst`.
- Package SHA-256: `5639c271359dd17236ce3f557832ee97885314ef8aa004b7892e399dc186a622`.

Built with makepkg as the unprivileged live user in Arch; all five packaged
Python modules and the session script matched checkout hashes. Official desktop
dependencies were installed with signature verification into the retained build
root; archiso 92-1 regenerated package/version lists, SquashFS and ISO. This was
an incremental build, not a second full bootstrap. The Linux 7.2.14 kernel and
boot chain from 0.3 were retained. Failed tmpfiles/hwdb hooks from the initial
unmounted-root package transaction were rerun successfully through arch-chroot.
No AUR package was included: the tray uses official-repository stalonetray.

## Automated checks

`./tests/run.sh`: **47 tests passed**:

- 12 GTK/Openbox UI tests, including power cancellation/denial, language indicator,
  tray-space reservation, desktop settings and existing launcher/task behavior;
- 7 keyboard tests using mocked Xlib and command execution;
- 6 isolated helper-lifecycle tests (all spawned helper PIDs stopped/reaped,
  missing optional commands, D-Bus activation, WM exit status);
- 9 hardware, 4 preferences, 4 desktop defaults, 4 live-readiness and 1 zram test.

Also passed Python compilation, shell syntax, Openbox XML and whitespace checks.
The keyboard wrapper was additionally exercised against a real Xvfb/Openbox XKB
server: EN → UK → UK on re-query → EN, not only against mocks.

## Booted ISO checks

QEMU software emulation, 2 vCPUs and 4096 MiB RAM, no data disk:

- The initial 0.4.0-1 image booted in **BIOS and OVMF UEFI** (Secure Boot off).
  Both passed live-session and desktop-helper checks.
- The final 0.4.0-2 image booted again in **BIOS** and passed both checks: ordinary
  user session, network/DNS, audio sockets, zram, keyring initialization,
  stalonetray/nm-applet/pasystray/power-manager/Dunst/authorization-agent processes,
  XKB status and the D-Bus notification service.
- Release 2 fixes a discovered stacking bug: the panel no longer covers the tray.
  Final-image screenshots show visible network/audio icons. Its boot chain is
  unchanged, but UEFI was not separately rerun for release 2.
- In the final live guest, keyboard CLI switched EN → UK and a subsequent query
  returned UK; the panel displayed UK. A notification was displayed and inspected.
- The power menu opened, selecting shutdown showed confirmation, and Escape
  cancelled without ending the session. Destructive power execution was mocked
  in tests, not presented as a physical reboot/poweroff test.
- Print opened Xfce Screenshooter's capture dialog. A separate explicit CLI
  capture saved a nonempty 1280×800 PNG in the test user's Pictures directory.
  No screenshot upload was performed.
- ARandR opened and displayed the virtual monitor. Its appearance was inspected;
  no claim is made about physical-monitor mode changes.

Fresh screenshots were captured from the final booted ISO and inspected. The
47-test suite and final package hashes, not historical screenshots alone, support
the implementation report.

## Limits

No physical battery, backlight, Wi-Fi adapter, USB media, suspend/resume or lid
behavior was available for testing. The VM is not evidence of those devices
working. The tray is XEmbed and currently laid out for one main screen. There is
no Feodal installer, persistent live storage or lock screen. Sleep is not a secure
lock. NVIDIA 580xx/PRIME and games on the MX330 remain unverified and unbundled.

Sources for version-sensitive behavior:
[stalonetray package](https://archlinux.org/packages/extra/x86_64/stalonetray/),
[Xfce Power Manager 4.20 foreground mode](https://docs.xfce.org/xfce/xfce4-power-manager/4.20/getting-started).
