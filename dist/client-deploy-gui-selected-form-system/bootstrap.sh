#!/usr/bin/env bash
# gui-selected-form-system ??bootstrap: ensure Python 3 + pip, then launch the install wizard.
# Run this FIRST on a fresh VM that may not have Python installed.
#   bash bootstrap.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" ; pwd)"

info() { echo "  $*"; }
die()  { echo "" >&2; echo "[ERROR] $*" >&2; exit 1; }

install_python() {
    # 1) Offline: install from bundled installers/ (drop .deb/.rpm there before transfer)
    if compgen -G "${SCRIPT_DIR}/installers/*.deb" >/dev/null 2>&1; then
        info "Installing Python from bundled .deb..."
        sudo dpkg -i "${SCRIPT_DIR}/installers/"*.deb || sudo apt-get install -f -y
        return
    fi
    if compgen -G "${SCRIPT_DIR}/installers/*.rpm" >/dev/null 2>&1; then
        info "Installing Python from bundled .rpm..."
        sudo rpm -Uvh --replacepkgs "${SCRIPT_DIR}/installers/"*.rpm || sudo yum localinstall -y "${SCRIPT_DIR}/installers/"*.rpm
        return
    fi
    # 2) Online: OS package manager
    if command -v apt-get >/dev/null 2>&1; then
        info "Installing Python via apt-get..."
        sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
    elif command -v dnf >/dev/null 2>&1; then
        info "Installing Python via dnf..."
        sudo dnf install -y python3 python3-pip
    elif command -v yum >/dev/null 2>&1; then
        info "Installing Python via yum..."
        sudo yum install -y python3 python3-pip
    else
        die "No bundled installer in installers/ and no package manager found. Install Python 3.11+ manually: https://www.python.org/downloads/"
    fi
}

if ! command -v python3 >/dev/null 2>&1; then
    info "Python 3 not found."
    install_python
    command -v python3 >/dev/null 2>&1 || die "Python install did not succeed. Install Python 3.11+ manually."
fi
info "Python: $(python3 --version 2>&1)"

if ! python3 -m pip --version >/dev/null 2>&1; then
    info "pip not found ??bootstrapping with ensurepip..."
    python3 -m ensurepip --upgrade || die "Could not install pip. Install python3-pip manually."
fi
info "pip: $(python3 -m pip --version 2>&1)"

echo ""
info "Launching install wizard..."
exec python3 "${SCRIPT_DIR}/install-wizard.py"