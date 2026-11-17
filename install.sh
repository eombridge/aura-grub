#!/usr/bin/env bash
# aura-grub installer — transparent, auditable GRUB2 theme installer
#
# System changes performed on install:
#   1. Copies theme assets to /boot/grub2/themes/<theme> (or /boot/grub/themes/<theme>)
#   2. Backs up /etc/default/grub -> /etc/default/grub.aura.bak (once)
#      and sets GRUB_THEME, GRUB_TIMEOUT, GRUB_DEFAULT, GRUB_GFXMODE
#   3. (--power-buttons) Appends UEFI Firmware, Reboot, Shut Down to /etc/grub.d/40_custom
#   4. Regenerates grub.cfg via grub2-mkconfig or update-grub
#
# Use --uninstall to revert /etc/default/grub, remove themes & power entries, and rebuild grub.cfg.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRUB_DEFAULT_FILE="/etc/default/grub"
GRUB_BACKUP_FILE="/etc/default/grub.aura.bak"
CUSTOM_40="/etc/grub.d/40_custom"
MARKER_START="# --- aura-grub power buttons start ---"
MARKER_END="# --- aura-grub power buttons end ---"

THEME="aura-light"
TIMEOUT="5"
DEFAULT_ENTRY="0"
POWER_BUTTONS=false
UNINSTALL=false

usage() {
    cat <<'EOF'
Usage: sudo ./install.sh [OPTIONS]

Options:
  --theme <aura-light|aura-dark>   Theme variant to install (default: aura-light)
  --timeout <seconds>              GRUB menu timeout in seconds (default: 5)
  --default <index|saved>          Default boot entry (default: 0)
  --power-buttons                  Add UEFI Firmware, Reboot, Shut Down entries
  --uninstall                      Restore backup and remove aura-grub completely
  -h, --help                       Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --theme)         THEME="${2:-}"; shift 2 ;;
        --timeout)       TIMEOUT="${2:-}"; shift 2 ;;
        --default)       DEFAULT_ENTRY="${2:-}"; shift 2 ;;
        --power-buttons) POWER_BUTTONS=true; shift ;;
        --uninstall)     UNINSTALL=true; shift ;;
        -h|--help)       usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [[ $EUID -ne 0 ]]; then
    echo "Error: please run with sudo (e.g., sudo ./install.sh)" >&2
    exit 1
fi

detect_grub_paths() {
    if [[ -d /boot/grub2 ]]; then
        THEME_BASE="/boot/grub2/themes"
        # Modern Fedora/RHEL (34+) stores the main config at /boot/grub2/grub.cfg even on UEFI
        GRUB_CFG="/boot/grub2/grub.cfg"
    elif [[ -d /boot/grub ]]; then
        THEME_BASE="/boot/grub/themes"
        GRUB_CFG="/boot/grub/grub.cfg"
    else
        echo "Error: neither /boot/grub2 nor /boot/grub found." >&2
        exit 1
    fi
}

rebuild_grub_cfg() {
    if command -v update-grub >/dev/null 2>&1; then
        update-grub
    elif command -v grub2-mkconfig >/dev/null 2>&1; then
        grub2-mkconfig -o "$GRUB_CFG"
    elif command -v grub-mkconfig >/dev/null 2>&1; then
        grub-mkconfig -o "$GRUB_CFG"
    else
        echo "Error: no grub2-mkconfig / grub-mkconfig / update-grub found." >&2
        exit 1
    fi
}

set_grub_var() {
    local key="$1" val="$2"
    if grep -qE "^#?${key}=" "$GRUB_DEFAULT_FILE"; then
        sed -i "s|^#*${key}=.*|${key}=${val}|" "$GRUB_DEFAULT_FILE"
    else
        echo "${key}=${val}" >> "$GRUB_DEFAULT_FILE"
    fi
}

remove_power_buttons() {
    if [[ -f "$CUSTOM_40" ]] && grep -qF "$MARKER_START" "$CUSTOM_40"; then
        sed -i "/${MARKER_START}/,/${MARKER_END}/d" "$CUSTOM_40"
    fi
}

add_power_buttons() {
    remove_power_buttons
    cat >> "$CUSTOM_40" <<EOF
${MARKER_START}
if [ "\${grub_platform}" = "efi" ]; then
    menuentry "UEFI Firmware" --class efi {
        fwsetup
    }
fi
menuentry "Reboot" --class restart {
    reboot
}
menuentry "Shut Down" --class shutdown {
    halt
}
${MARKER_END}
EOF
    chmod +x "$CUSTOM_40"
}

detect_grub_paths

if [[ "$UNINSTALL" == true ]]; then
    echo "Uninstalling aura-grub..."
    rm -rf "${THEME_BASE}/aura-light" "${THEME_BASE}/aura-dark"
    remove_power_buttons
    if [[ -f "$GRUB_BACKUP_FILE" ]]; then
        cp -a "$GRUB_BACKUP_FILE" "$GRUB_DEFAULT_FILE"
        rm -f "$GRUB_BACKUP_FILE"
        echo "Restored $GRUB_DEFAULT_FILE from $GRUB_BACKUP_FILE"
    fi
    rebuild_grub_cfg
    echo "Done. aura-grub has been removed."
    exit 0
fi

if [[ "$THEME" != "aura-light" && "$THEME" != "aura-dark" ]]; then
    echo "Error: --theme must be 'aura-light' or 'aura-dark'" >&2
    exit 1
fi

SRC_THEME="${SCRIPT_DIR}/themes/${THEME}"
if [[ ! -d "$SRC_THEME" ]]; then
    echo "Error: theme directory not found: $SRC_THEME" >&2
    exit 1
fi

[[ -f "$GRUB_BACKUP_FILE" ]] || cp -a "$GRUB_DEFAULT_FILE" "$GRUB_BACKUP_FILE"

mkdir -p "$THEME_BASE"
rm -rf "${THEME_BASE:?}/${THEME}"
cp -r "$SRC_THEME" "${THEME_BASE}/${THEME}"

set_grub_var "GRUB_THEME" "\"${THEME_BASE}/${THEME}/theme.txt\""
set_grub_var "GRUB_TIMEOUT" "$TIMEOUT"
set_grub_var "GRUB_DEFAULT" "$DEFAULT_ENTRY"
set_grub_var "GRUB_GFXMODE" "\"1920x1080,auto\""
set_grub_var "GRUB_TERMINAL_OUTPUT" "\"gfxterm\""

if [[ "$POWER_BUTTONS" == true ]]; then
    add_power_buttons
fi

rebuild_grub_cfg
echo "Installed ${THEME} -> ${THEME_BASE}/${THEME}"
