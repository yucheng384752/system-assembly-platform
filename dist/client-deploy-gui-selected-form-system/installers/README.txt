Offline Python installers
=========================

If the target machine has NO internet AND no Python 3, drop the matching
Python installer here BEFORE transferring this package. bootstrap.sh /
bootstrap.ps1 will detect and install from this folder automatically.

  Windows       : python-3.11.x-amd64.exe (or .msi)
                  https://www.python.org/downloads/windows/
  Ubuntu/Debian : python3, python3-pip, python3-venv .deb files
                  (on a same-version online box: apt-get download python3 python3-pip python3-venv)
  RHEL/CentOS   : python3, python3-pip .rpm files

If the machine HAS internet, ignore this folder ??bootstrap installs Python
via the OS package manager (apt/dnf/yum) or winget.