#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ACTION=${1:-build}
DERIVED_DATA=${TMPDIR:-/tmp}/stock-manager-ios-derived
TEST_DESTINATION=${IOS_TEST_DESTINATION:-platform=iOS Simulator,name=iPhone 17}

case "$ACTION" in
  build)
    xcodebuild -project "$ROOT_DIR/StockManager.xcodeproj" -scheme StockManager -configuration Debug -destination 'generic/platform=iOS' -derivedDataPath "$DERIVED_DATA" CODE_SIGNING_ALLOWED=NO build
    ;;
  test)
    xcodebuild -project "$ROOT_DIR/StockManager.xcodeproj" -scheme StockManager -configuration Debug -destination "$TEST_DESTINATION" -derivedDataPath "$DERIVED_DATA" test
    ;;
  *)
    echo "usage: $0 [build|test]" >&2
    exit 2
    ;;
esac
