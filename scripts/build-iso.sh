#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
    printf 'Usage: %s /path/to/feodal-shell-*.pkg.tar.zst [output-directory]\n' "${0##*/}" >&2
}

die() {
    printf 'build-iso: %s\n' "$*" >&2
    exit 1
}

if [[ $# -lt 1 || $# -gt 2 ]]; then
    usage
    exit 2
fi

[[ -r /etc/arch-release ]] || die 'must run on an Arch Linux host'
(( EUID == 0 )) || die 'must run as root (mkarchiso requirement)'

for command in pacman repo-add mkarchiso cp mkdir mktemp realpath sed; do
    command -v "$command" >/dev/null 2>&1 || die "required command not found: $command"
done

releng_profile=${ARCHISO_RELENG_PROFILE:-/usr/share/archiso/configs/releng}
[[ -d $releng_profile && -f $releng_profile/profiledef.sh && -f $releng_profile/pacman.conf && -f $releng_profile/packages.x86_64 ]] ||
    die "Arch releng profile not found or incomplete: $releng_profile (install archiso)"

package_path=$(realpath -e -- "$1") || die "package does not exist: $1"
[[ -f $package_path ]] || die "not a regular package file: $package_path"
package_info=$(pacman -Qp -- "$package_path") || die 'pacman could not read the package archive'
[[ ${package_info%% *} == feodal-shell ]] || die "expected a feodal-shell package, got: ${package_info%% *}"

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
overlay_dir="$script_dir/iso/overlay/airootfs"
[[ -d $overlay_dir ]] || die "ISO overlay not found: $overlay_dir"

output_arg=${2:-"$PWD/out"}
mkdir -p -- "$output_arg"
out_dir=$(cd -- "$output_arg" && pwd -P)
releng_real=$(cd -- "$releng_profile" && pwd -P)
case "$out_dir/" in
    "$releng_real/"*) die 'output directory must not be inside the installed releng profile' ;;
esac

work_root=$(mktemp -d "${TMPDIR:-/tmp}/feodal-iso.XXXXXXXX")
# Pacman's unprivileged downloader must traverse the local package repository.
chmod 0755 "$work_root"
# Failed builds can leave mounts below work; never recursively delete that tree.
trap 'printf "Build workspace retained for inspection: %s\n" "$work_root" >&2' EXIT

profile="$work_root/profile"
repo_dir="$work_root/local-repo"
mkdir -p -- "$profile" "$repo_dir" "$work_root/work"
cp -a -- "$releng_profile/." "$profile/"
cp -a -- "$overlay_dir/." "$profile/airootfs/"
# Steam needs multilib at build time as well as in the installed system.
sed -i -e 's/^#\[multilib\]/[multilib]/' "$profile/pacman.conf"
if ! grep -q '^\[multilib\]' "$profile/pacman.conf"; then
    printf '\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n' >> "$profile/pacman.conf"
else
    sed -i '/^\[multilib\]/,/^$/s/^#Include/Include/' "$profile/pacman.conf"
fi
sed -i \
    -e 's/^iso_name=.*/iso_name="feodal"/' \
    -e 's/^iso_label=.*/iso_label="FEODAL"/' \
    -e 's/^iso_publisher=.*/iso_publisher="Feodal Linux"/' \
    -e 's/^iso_application=.*/iso_application="Feodal Linux live prototype"/' \
    "$profile/profiledef.sh"
cat >> "$profile/profiledef.sh" <<'PROFILE_EOF'

# Keep the Steam/multilib image within the release hosting size limit.
airootfs_image_tool_options=('-comp' 'zstd' '-Xcompression-level' '19' '-b' '1M')
PROFILE_EOF
printf '\niso_version=%q\n' "${package_info#* }" >> "$profile/profiledef.sh"
grep -q '^iso_name="feodal"$' "$profile/profiledef.sh" || die 'could not customize releng profile metadata'

package_copy="$repo_dir/${package_path##*/}"
cp -- "$package_path" "$package_copy"
repo-add "$repo_dir/feodal-local.db.tar.gz" "$package_copy"
cat >> "$profile/pacman.conf" <<PACMAN_EOF

[feodal-local]
SigLevel = Optional TrustAll
Server = file://$repo_dir
PACMAN_EOF

add_package() {
    local package=$1
    grep -Fxq -- "$package" "$profile/packages.x86_64" || printf '%s\n' "$package" >> "$profile/packages.x86_64"
}
for package in feodal-shell openbox xorg-server xorg-xinit gtk3 python python-gobject networkmanager zram-generator pipewire pipewire-pulse wireplumber; do
    add_package "$package"
done

while IFS= read -r package || [[ -n $package ]]; do
    [[ -z $package || $package == \#* ]] || add_package "$package"
done < "$script_dir/iso/packages.desktop"

mkarchiso -v -w "$work_root/work" -o "$out_dir" "$profile"
printf 'ISO build complete. Artifacts: %s\n' "$out_dir"
