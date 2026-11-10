# Feodal Linux ISO prototype

This prototype builds an x86_64 live ISO from the installed Arch Linux `releng` archiso profile. It uses Arch's standard `linux` kernel and adds the locally built `feodal-shell` package plus Openbox, Xorg/Xinit, GTK 3, Python/GObject, and NetworkManager from the official repositories. NetworkManager is enabled in the live environment and uses systemd-resolved for DNS. The inherited systemd-networkd service/socket and standalone iwd service are masked to prevent competing network managers. SSH is masked by default; the live system does not expose a remote login service. PipeWire, pipewire-pulse and WirePlumber provide the audio stack.

Desktop packages are listed in `iso/packages.desktop`: official Arch Firefox,
Ukrainian language pack, Mousepad, Xarchiver, ZIP/unzip, mpv and Noto/emoji fonts.
Version 0.6 also bundles Steam, 64-/32-bit Intel Vulkan/Mesa, GameMode, kernel
headers/DKMS, Bluetooth tools and i3lock/xss-lock. Multilib is enabled in both
the build profile and the installed system; official package signatures remain required.
The browser homepage is local and user-editable; only its first-run tour is hidden.
Firefox security isolation and updates are not disabled. See [browser defaults](browser.md).
These applications are not autostarted by the session. Feodal 0.4 adds dedicated
session helpers for the XEmbed tray, network/audio indicators, power management,
notifications and policy authorization; see [desktop behavior](desktop.md).
Run `scripts/check-desktop-session.sh` as root inside the booted VM to verify
these helper processes and notification/XKB services without triggering power
actions or changing hardware settings.

The live filesystem uses zstd level 19 to fit the Steam/multilib image under the release hosting limit; the initramfs uses zstd level 6. Higher root-image compression costs build time without changing the installed files. The initramfs retains local-media boot hooks but omits PXE/NFS/HTTP/NBD boot support; this profile is for local ISO/USB boot, not netboot.

The live profile uses `zram-generator` with zstd, a logical swap size of half RAM capped at 4096 MiB, and priority 100. Compressed pages still use physical memory; this is not extra RAM or an FPS guarantee. The live account is the unprivileged `feodal` user; tty1 logs it in automatically and starts `feodal-session` through Xinit. If X fails, the user is left at a console prompt.

## Build

Build `feodal-shell` first with Arch packaging tools. On an Arch Linux build host (or an Arch virtual machine), install the `archiso` package and ensure `pacman`, `repo-add`, and `mkarchiso` are available. The script must run as root because `mkarchiso` requires it; it does not install packages on the host or write to a target disk. It downloads packages only through the standard pacman repositories configured by releng and retains its temporary work directory for inspection. It never recursively deletes the work tree: an interrupted mkarchiso run may leave mounts there. The directory path is printed on exit; check for mounted filesystems before manually cleaning it.

```sh
sudo ./scripts/build-iso.sh /path/to/feodal-shell-<version>-any.pkg.tar.* [output-directory]
```

The image filename uses the shell package version (for example,
`feodal-0.6.0-1-x86_64.iso`) so different package versions do not overwrite the
previous dated prototype.

The output directory defaults to `./out` and is not cleaned or deleted. The package must have the `feodal-shell` package name; it is staged in a temporary local file repository created with `repo-add`, allowing pacman to resolve the shell and its official repository dependencies. Pass a locally built package you trust. The installed releng profile can be selected with `ARCHISO_RELENG_PROFILE` if it is not at `/usr/share/archiso/configs/releng`.

Boot the resulting ISO as a live system. Since 0.5 the live session has a graphical Feodal installer that erases one selected whole disk; see [installer](installer.md). Arch releng installation/rescue utilities remain in the live image but are not the Feodal installation path. It is not a claim of hardware compatibility, and physical hardware remains untested. The initial 0.4.0-1 image was boot-tested in BIOS and UEFI QEMU; the final 0.4.0-2 tray-layout fix was retested in BIOS. See [current verification](verification-0.4.md) and [0.3 verification](verification-0.3.md). Earlier images have separate [0.2](verification-0.2.md) and [0.1](verification.md) verification records.

## NVIDIA and hardware caveats

No proprietary NVIDIA driver, legacy 580xx AUR package, or other AUR package is bundled. In particular, do not assume NVIDIA MX330 support: it may require a legacy driver path such as 580xx, which is outside this prototype and is not validated here. Physical hardware support remains untested; no compatibility guarantee is made.

## Virtual-machine smoke test

On an Arch host install `qemu-system-x86`; on Ubuntu/Debian run
`sudo ./scripts/setup-ui-tests.sh --with-vm` to install verification tools.
From a graphical session:

```sh
./scripts/boot-vm.sh out/feodal-<version>-x86_64.iso
```

The script boots the ISO with software emulation, 4 GiB RAM and **no attached host
or virtual hard disk**. It does not install or modify the host operating system.
No SSH forwarding is enabled. Close QEMU to discard the ephemeral live session.
Software rendering/emulation is not suitable for measuring game FPS.

Check that tty1 opens the Feodal desktop as user `feodal`, the launcher opens and
starts a terminal, networking has a single manager, audio services are running,
and `zramctl` plus `swapon --show` list `/dev/zram0`. None of these tests validates
the proprietary NVIDIA driver or a physical Wi-Fi/audio device.

Run `scripts/check-live-session.sh` as root **inside** the booted live system for
the service/session smoke checks. The script checks read-only state; it does not
install drivers, change partitions, or validate physical audio output. Secure Boot
signing is not configured for this prototype.

Before running pacman in a freshly booted live system, let `pacman-init.service`
finish setting up its temporary keyring. Do not run pacman/key import operations
concurrently with initialization. `scripts/check-live-session.sh` waits up to
180 seconds for this step and fails if initialization did not succeed; it does
not bypass signature verification or import arbitrary keys.
