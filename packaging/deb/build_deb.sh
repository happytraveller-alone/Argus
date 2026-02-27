#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEB_DIR="$ROOT_DIR/packaging/deb"
PACKAGE_NAME="deepaudit"
VERSION=""
ARCH="amd64"
OUTPUT_DIR="$ROOT_DIR/dist"

usage() {
  cat <<USAGE
Usage: $0 --version <x.y.z> [--arch amd64|arm64] [--output <dir>]
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      VERSION="${2:-}"
      shift 2
      ;;
    --arch)
      ARCH="${2:-}"
      shift 2
      ;;
    --output)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$VERSION" ]]; then
  echo "[ERROR] --version is required"
  usage
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "[ERROR] dpkg-deb is required"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

STAGING_DIR="$TMP_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}"
mkdir -p "$STAGING_DIR" "$STAGING_DIR/DEBIAN"

cp -R "$DEB_DIR/rootfs/." "$STAGING_DIR/"

# Always bundle current compose templates from repository.
cp "$ROOT_DIR/docker-compose.prod.yml" "$STAGING_DIR/etc/deepaudit/docker-compose.prod.yml"
cp "$ROOT_DIR/docker-compose.prod.cn.yml" "$STAGING_DIR/etc/deepaudit/docker-compose.prod.cn.yml"

# Remove hard-coded ports from bundled compose; runtime ports come from override file.
for compose_file in \
  "$STAGING_DIR/etc/deepaudit/docker-compose.prod.yml" \
  "$STAGING_DIR/etc/deepaudit/docker-compose.prod.cn.yml"; do
  perl -0pi -e 's/\n    ports:\n      - "8000:8000"\n/\n/g' "$compose_file"
  perl -0pi -e 's/\n    ports:\n      - "3000:80"\n/\n/g' "$compose_file"
  perl -0pi -e 's#(ghcr(?:\.nju\.edu\.cn)?/lintsinghua/deepaudit-[^:]+):latest#$1:\${DEEPAUDIT_IMAGE_TAG:-latest}#g' "$compose_file"
done

sed \
  -e "s/__VERSION__/${VERSION}/g" \
  -e "s/__ARCH__/${ARCH}/g" \
  "$DEB_DIR/debian/control" > "$STAGING_DIR/DEBIAN/control"

cp "$DEB_DIR/debian/conffiles" "$STAGING_DIR/DEBIAN/conffiles"
cp "$DEB_DIR/debian/postinst" "$STAGING_DIR/DEBIAN/postinst"
cp "$DEB_DIR/debian/prerm" "$STAGING_DIR/DEBIAN/prerm"
cp "$DEB_DIR/debian/postrm" "$STAGING_DIR/DEBIAN/postrm"

chmod 0755 "$STAGING_DIR/DEBIAN/postinst" "$STAGING_DIR/DEBIAN/prerm" "$STAGING_DIR/DEBIAN/postrm"
chmod 0755 "$STAGING_DIR/usr/bin/deepauditctl"

mkdir -p "$OUTPUT_DIR"
OUTPUT_FILE="$OUTPUT_DIR/${PACKAGE_NAME}_${VERSION}_${ARCH}.deb"

dpkg-deb --build "$STAGING_DIR" "$OUTPUT_FILE"

echo "[INFO] built package: $OUTPUT_FILE"
dpkg-deb --info "$OUTPUT_FILE"
dpkg-deb --contents "$OUTPUT_FILE" | head -n 200
