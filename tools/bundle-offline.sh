#!/usr/bin/env bash
# bundle-offline.sh — 在有網路的機器上執行，產生離線安裝包
#
# 用途：
#   工廠機器無法聯網時，先在開發機執行此腳本，
#   將 Docker 映像與 Docker 安裝包一起打包，再用 USB 帶入目標機器。
#
# 使用方式：
#   chmod +x tools/bundle-offline.sh
#   ./tools/bundle-offline.sh [client-deploy-dir] [output-dir]
#
# 範例：
#   ./tools/bundle-offline.sh dist/client-deploy-gui-selected-form-system /tmp/offline-bundle

set -euo pipefail

DEPLOY_DIR="${1:-dist/client-deploy-gui-selected-form-system}"
OUTPUT_DIR="${2:-dist/offline-bundle}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

DEPLOY_PATH="$REPO_ROOT/$DEPLOY_DIR"
OUTPUT_PATH="$REPO_ROOT/$OUTPUT_DIR"

echo "=== Form System 離線包打包工具 ==="
echo "來源: $DEPLOY_PATH"
echo "輸出: $OUTPUT_PATH"
echo ""

# ── 1. 確認 Docker 可用 ────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo "✗ 需要 Docker。請先在有網路的機器安裝 Docker 再執行此腳本。"
    exit 1
fi

mkdir -p "$OUTPUT_PATH/docker-images"
mkdir -p "$OUTPUT_PATH/system"

# ── 2. 決定需要的映像 ──────────────────────────────────────────────────────
# 從 docker-compose.yml 或 deploy.sh 讀取映像名稱（若有變動請手動更新）
IMAGES=(
    "postgres:15-alpine"
    "nginx:alpine"
    "python:3.11-slim"
    "node:20-slim"
)

echo ">> 拉取並儲存 Docker 映像..."
for img in "${IMAGES[@]}"; do
    echo "   pulling $img"
    docker pull "$img"
done

echo "   saving images to docker-images/images.tar.gz"
docker save "${IMAGES[@]}" | gzip > "$OUTPUT_PATH/docker-images/images.tar.gz"
echo "   $(du -sh "$OUTPUT_PATH/docker-images/images.tar.gz" | cut -f1)  docker-images/images.tar.gz"

# ── 3. 複製部署包 ──────────────────────────────────────────────────────────
echo ""
echo ">> 複製部署包..."
cp -r "$DEPLOY_PATH/." "$OUTPUT_PATH/system/"

# ── 4. 寫入 offline 旗標（讓 install-wizard 知道要 load 而非 pull）────────
echo "offline" > "$OUTPUT_PATH/system/.offline-mode"

# ── 5. 產生 Docker Engine 安裝指引 ────────────────────────────────────────
cat > "$OUTPUT_PATH/INSTALL-DOCKER-OFFLINE.sh" <<'EOF'
#!/usr/bin/env bash
# 在目標機器（無網路）上安裝 Docker Engine（Ubuntu/Debian）
# 需提前下載 .deb 套件並放在 docker-debs/ 目錄
#
# 下載指令（在有網路的機器執行）：
#   apt-get download docker-ce docker-ce-cli containerd.io docker-compose-plugin
#   # 或從 https://download.docker.com/linux/<distro>/dists/ 手動下載

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -d "$SCRIPT_DIR/docker-debs" ]; then
    echo ">> 安裝 Docker Engine (離線 .deb)..."
    sudo dpkg -i "$SCRIPT_DIR/docker-debs"/*.deb
    sudo systemctl enable docker
    sudo systemctl start docker
else
    echo "docker-debs/ 目錄不存在，跳過 Docker 安裝。"
    echo "請確認目標機器已安裝 Docker。"
fi

echo ""
echo ">> 載入 Docker 映像..."
docker load < "$SCRIPT_DIR/docker-images/images.tar.gz"
echo "映像載入完成："
docker images --format "  {{.Repository}}:{{.Tag}}  ({{.Size}})"
EOF
chmod +x "$OUTPUT_PATH/INSTALL-DOCKER-OFFLINE.sh"

# ── 6. 顯示摘要 ───────────────────────────────────────────────────────────
echo ""
echo "=== 打包完成 ==="
echo "輸出目錄: $OUTPUT_PATH"
du -sh "$OUTPUT_PATH"
echo ""
echo "目標機器安裝步驟："
echo "  1. 把 $OUTPUT_DIR 整個資料夾複製到 USB"
echo "  2. 在目標機器執行: ./INSTALL-DOCKER-OFFLINE.sh"
echo "  3. 執行: python3 system/install-wizard.py"
