#!/usr/bin/env bash

# This script installs the LLVM dependencies for Debian-based distros (e.g. Ubuntu).
LLVM_VERSION=22
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $0 [--dry-run|-n] [--help|-h]

Installs the LLVM/Flang ${LLVM_VERSION} build dependencies on Debian/Ubuntu.

Options:
  -n, --dry-run   Print the commands instead of executing them.
  -h, --help      Show this help message.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        -n|--dry-run)
            DRY_RUN=1
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
    shift
done

run() {
    if [ "${DRY_RUN}" -eq 1 ]; then
        printf '+'
        printf ' %q' "$@"
        printf '\n'
    else
        "$@"
    fi
}

check_package() {
    local package="$1"
    local display_name="${2:-$1}"
    if dpkg -l | grep -q "${package}"; then
        echo "${display_name} is installed."
    else
        echo "${display_name} is not installed."
    fi
}

check_tool() {
    local tool="$1"
    local display_name="${2:-$1}"
    if command -v "${tool}" &> /dev/null; then
        echo "${display_name} is available."
    else
        echo "${display_name} is not available."
    fi
}

# Update the package list
run apt update -y

# Install needed packages
run env DEBIAN_FRONTEND=noninteractive apt install -y wget lsb-release gnupg software-properties-common

# Run the LLVM installation script
run wget https://apt.llvm.org/llvm.sh -O /tmp/llvm.sh
run chmod +x /tmp/llvm.sh
run /tmp/llvm.sh "${LLVM_VERSION}"

# Check if script was successful
if [ $? -ne 0 ]; then
    echo "LLVM base installation failed."
    exit 1
fi

# Required dependencies
PKG="flang-${LLVM_VERSION} libflang-${LLVM_VERSION}-dev llvm-${LLVM_VERSION}-dev libmlir-${LLVM_VERSION}-dev mlir-${LLVM_VERSION}-tools libclang-${LLVM_VERSION}-dev"

# Development dependencies
PKG="$PKG cmake clang-${LLVM_VERSION}"

run apt install -y $PKG
INSTALL_STATUS=$?

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "Dry run completed; no changes were made."
    exit 0
fi

# Check if the installation was successful
if [ "${INSTALL_STATUS}" -eq 0 ]; then
    echo "Dependency installation completed successfully."
else
    echo "Dependency installation failed."
    exit 1
fi


# Check if the LLVM packages are installed
check_package "flang-${LLVM_VERSION}" "Flang"
check_package "libflang-${LLVM_VERSION}-dev"
check_package "llvm-${LLVM_VERSION}-dev"
check_package "libmlir-${LLVM_VERSION}-dev"
check_package "mlir-${LLVM_VERSION}-tools"


# Check if the LLVM tools are available
check_tool "flang-${LLVM_VERSION}" "Flang tool"
check_tool "llvm-config-${LLVM_VERSION}" "LLVM config tool"
check_tool "mlir-opt-${LLVM_VERSION}" "MLIR opt tool"
