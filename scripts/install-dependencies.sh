#!/usr/bin/env bash
set -euo pipefail

# This script installs the LLVM dependencies for Debian-based distros (e.g Ubuntu).
LLVM_VERSION=22

# Update the package list
apt-get update

# Install needed packages
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    wget lsb-release gnupg software-properties-common ca-certificates \
    python3 python3-protobuf protobuf-compiler libprotobuf-dev

# Run the LLVM installation script
wget https://apt.llvm.org/llvm.sh -O /tmp/llvm.sh
chmod +x /tmp/llvm.sh
if ! /tmp/llvm.sh "${LLVM_VERSION}"; then
    echo "LLVM base installation failed."
    exit 1
fi

packages=(
    "flang-${LLVM_VERSION}"
    "libflang-${LLVM_VERSION}-dev"
    "llvm-${LLVM_VERSION}-dev"
    "llvm-${LLVM_VERSION}-linker-tools"
    "libmlir-${LLVM_VERSION}-dev"
    "mlir-${LLVM_VERSION}-tools"
    "libclang-${LLVM_VERSION}-dev"
    cmake
    make
    g++
    "clang-${LLVM_VERSION}"
)
DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"

if [ ! -f "/usr/lib/llvm-${LLVM_VERSION}/lib/libLTO.so.22.1" ]; then
    echo "LLVM ${LLVM_VERSION} development files are missing libLTO.so.22.1; install llvm-${LLVM_VERSION}-linker-tools."
    exit 1
fi

for tool in "flang-${LLVM_VERSION}" "llvm-config-${LLVM_VERSION}" "mlir-opt-${LLVM_VERSION}"; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "Required LLVM tool is unavailable: ${tool}"
        exit 1
    fi
done

echo "LLVM ${LLVM_VERSION}, protobuf, and Python dependencies are installed."
