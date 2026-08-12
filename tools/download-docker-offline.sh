#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# download-docker-offline.sh — 自動偵測 OS 並下載 Docker Engine 離線包
#
# 用法：
#   # Stage 1：在目標機器（無網路）偵測 OS，輸出偵測結果
#   bash download-docker-offline.sh --detect-only
#
#   # Stage 2：在有網路的機器下載（使用 Stage 1 的輸出）
#   bash download-docker-offline.sh --download ubuntu jammy amd64 ./offline-docker/
#
#   # 一站式（目標機器有網路，或測試用）
#   bash download-docker-offline.sh --auto ./offline-docker/
#
#   # 在目標機器安裝（離線）
#   bash download-docker-offline.sh --install ./offline-docker/
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[OK]${NC}   $1"; }
info() { echo -e "${CYAN}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC}  $1"; exit 1; }

# ── 版本對照表 ────────────────────────────────────────────────────────────────
# 格式：distro:codename:arch → base URL
declare -A DOCKER_URLS=(
  ["ubuntu:jammy:amd64"]="https://download.docker.com/linux/ubuntu/dists/jammy/pool/stable/amd64"
  ["ubuntu:jammy:arm64"]="https://download.docker.com/linux/ubuntu/dists/jammy/pool/stable/arm64"
  ["ubuntu:focal:amd64"]="https://download.docker.com/linux/ubuntu/dists/focal/pool/stable/amd64"
  ["ubuntu:focal:arm64"]="https://download.docker.com/linux/ubuntu/dists/focal/pool/stable/arm64"
  ["ubuntu:noble:amd64"]="https://download.docker.com/linux/ubuntu/dists/noble/pool/stable/amd64"
  ["ubuntu:noble:arm64"]="https://download.docker.com/linux/ubuntu/dists/noble/pool/stable/arm64"
  ["debian:bookworm:amd64"]="https://download.docker.com/linux/debian/dists/bookworm/pool/stable/amd64"
  ["debian:bookworm:arm64"]="https://download.docker.com/linux/debian/dists/bookworm/pool/stable/arm64"
  ["debian:bullseye:amd64"]="https://download.docker.com/linux/debian/dists/bullseye/pool/stable/amd64"
)

# ── OS 偵測函式 ───────────────────────────────────────────────────────────────
detect_os() {
  local distro="" codename="" arch=""

  if command -v lsb_release &>/dev/null; then
    distro=$(lsb_release -si 2>/dev/null | tr '[:upper:]' '[:lower:]')
    codename=$(lsb_release -sc 2>/dev/null | tr '[:upper:]' '[:lower:]')
  elif [[ -f /etc/os-release ]]; then
    distro=$(. /etc/os-release && echo "${ID:-}" | tr '[:upper:]' '[:lower:]')
    codename=$(. /etc/os-release && echo "${VERSION_CODENAME:-}" | tr '[:upper:]' '[:lower:]')
  fi

  arch=$(uname -m)
  case "$arch" in
    x86_64)  arch="amd64";;
    aarch64) arch="arm64";;
    armv7l)  arch="armhf";;
    *)       arch="$arch";;
  esac

  echo "distro=$distro codename=$codename arch=$arch"
}

# ── 最新版本號擷取（從 Docker 下載頁面解析）─────────────────────────────────
fetch_latest_version() {
  local base_url="$1"
  local pkg="$2"
  # 取得目錄列表，找最新版本
  curl -sf "$base_url/" 2>/dev/null \
    | grep -oP "(?<=\")${pkg}_[0-9]+\.[0-9]+\.[0-9]+-[0-9]+[^\"]*\.deb(?=\")" \
    | sort -V | tail -1
}

# ── 下載函式 ──────────────────────────────────────────────────────────────────
download_packages() {
  local distro="$1" codename="$2" arch="$3" out_dir="$4"
  local key="${distro}:${codename}:${arch}"

  local base_url="${DOCKER_URLS[$key]:-}"
  if [[ -z "$base_url" ]]; then
    err "不支援的組合：$key\n  支援的組合：\n$(printf '    %s\n' "${!DOCKER_URLS[@]}" | sort)"
  fi

  mkdir -p "$out_dir"
  info "下載目標：$base_url"
  info "輸出目錄：$out_dir"
  echo ""

  local PKGS=(containerd.io docker-ce-cli docker-ce docker-buildx-plugin docker-compose-plugin)
  local downloaded=0

  for pkg in "${PKGS[@]}"; do
    info "搜尋 $pkg …"
    local filename
    filename=$(fetch_latest_version "$base_url" "$pkg")

    if [[ -z "$filename" ]]; then
      warn "$pkg：找不到版本，跳過（請手動確認）"
      continue
    fi

    local url="${base_url}/${filename}"
    local dest="${out_dir}/${filename}"

    if [[ -f "$dest" ]]; then
      ok "$pkg 已存在：$filename"
    else
      info "下載：$filename"
      if curl -fL -o "$dest" "$url" --progress-bar; then
        ok "$pkg 下載完成：$filename"
        ((downloaded++))
      else
        warn "$pkg 下載失敗，URL：$url"
      fi
    fi
  done

  echo ""
  info "完成。下載 $downloaded 個套件至 $out_dir"
  echo ""
  echo "  離線安裝指令："
  echo "    sudo dpkg -i ${out_dir}containerd.io_*.deb"
  echo "    sudo dpkg -i ${out_dir}docker-ce-cli_*.deb"
  echo "    sudo dpkg -i ${out_dir}docker-ce_*.deb"
  echo "    sudo dpkg -i ${out_dir}docker-buildx-plugin_*.deb"
  echo "    sudo dpkg -i ${out_dir}docker-compose-plugin_*.deb"
  echo "    sudo systemctl enable --now docker"
}

# ── 安裝函式（離線，目標機器執行）────────────────────────────────────────────
install_offline() {
  local pkg_dir="$1"
  [[ -d "$pkg_dir" ]] || err "找不到目錄：$pkg_dir"

  local debs=("$pkg_dir"/*.deb)
  [[ ${#debs[@]} -eq 0 ]] && err "$pkg_dir 中沒有 .deb 檔案"

  info "安裝 ${#debs[@]} 個套件 from $pkg_dir"
  local order=(containerd.io docker-ce-cli docker-ce docker-buildx-plugin docker-compose-plugin)

  for pkg in "${order[@]}"; do
    local deb
    deb=$(ls "$pkg_dir"/${pkg}_*.deb 2>/dev/null | sort -V | tail -1 || true)
    if [[ -n "$deb" ]]; then
      info "安裝 $(basename "$deb")"
      sudo dpkg -i "$deb" || warn "dpkg 回傳錯誤，可能是依賴問題，嘗試 apt-get -f install"
    fi
  done

  if ! command -v docker &>/dev/null; then
    warn "docker 指令未找到，嘗試修復依賴：sudo apt-get install -f"
  else
    ok "Docker 安裝完成：$(docker --version)"
    sudo systemctl enable docker --now 2>/dev/null && ok "Docker 服務已啟用" || true
  fi
}

# ── 主程式 ────────────────────────────────────────────────────────────────────
MODE="${1:-}"

case "$MODE" in
  --detect-only)
    echo "════════════════════════════════════════════"
    echo "  OS 偵測結果（複製到有網路的機器使用）"
    echo "════════════════════════════════════════════"
    detect_os
    ;;

  --download)
    [[ $# -lt 5 ]] && err "用法：$0 --download <distro> <codename> <arch> <output_dir>"
    download_packages "$2" "$3" "$4" "$5"
    ;;

  --auto)
    OUT_DIR="${2:-./offline-docker/}"
    echo "════════════════════════════════════════════"
    echo "  自動偵測 + 下載 Docker Engine 離線包"
    echo "════════════════════════════════════════════"
    eval "$(detect_os)"
    info "偵測到：distro=$distro  codename=$codename  arch=$arch"
    echo ""
    download_packages "$distro" "$codename" "$arch" "$OUT_DIR"
    ;;

  --install)
    [[ $# -lt 2 ]] && err "用法：$0 --install <package_dir>"
    install_offline "$2"
    ;;

  *)
    echo "Docker Engine 離線包下載工具"
    echo ""
    echo "用法："
    echo "  # Stage 1：在目標機器偵測 OS"
    echo "  bash $0 --detect-only"
    echo ""
    echo "  # Stage 2：在有網路的機器下載"
    echo "  bash $0 --download ubuntu jammy amd64 ./offline-docker/"
    echo ""
    echo "  # 一站式（機器有網路）"
    echo "  bash $0 --auto ./offline-docker/"
    echo ""
    echo "  # 安裝（離線，目標機器）"
    echo "  bash $0 --install ./offline-docker/"
    echo ""
    echo "支援的 distro:codename:arch 組合："
    printf '  %s\n' "${!DOCKER_URLS[@]}" | sort
    ;;
esac
