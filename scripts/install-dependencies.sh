#!/usr/bin/env bash

# This script installs the LLVM dependencies for Ubuntu.

LLVM_VERSION=20

./llvm.sh ${LLVM_VERSION}

apt install -y flang-${LLVM_VERSION} libflang-${LLVM_VERSION}-dev llvm-${LLVM_VERSION}-dev libmlir-${LLVM_VERSION}-dev mlir-${LLVM_VERSION}-tools
apt install -y cmake


# Check if the installation was successful
if [ $? -eq 0 ]; then
    echo "LLVM installation completed successfully."
else
    echo "LLVM installation failed."
    exit 1
fi


# Check if the LLVM packages are installed
if dpkg -l | grep -q "flang-${LLVM_VERSION}"; then
    echo "Flang is installed."
else
    echo "Flang is not installed."
fi
if dpkg -l | grep -q "libflang-${LLVM_VERSION}-dev"; then
    echo "libflang-${LLVM_VERSION}-dev is installed."
else
    echo "libflang-${LLVM_VERSION}-dev is not installed."
fi
if dpkg -l | grep -q "llvm-${LLVM_VERSION}-dev"; then
    echo "llvm-${LLVM_VERSION}-dev is installed."
else
    echo "llvm-${LLVM_VERSION}-dev is not installed."
fi
if dpkg -l | grep -q "libmlir-${LLVM_VERSION}-dev"; then
    echo "libmlir-${LLVM_VERSION}-dev is installed."
else
    echo "libmlir-${LLVM_VERSION}-dev is not installed."
fi
if dpkg -l | grep -q "mlir-${LLVM_VERSION}-tools"; then
    echo "mlir-${LLVM_VERSION}-tools is installed."
else
    echo "mlir-${LLVM_VERSION}-tools is not installed."
fi


# Check if the LLVM tools are available
if command -v flang-${LLVM_VERSION} &> /dev/null; then
    echo "Flang tool is available."
else
    echo "Flang tool is not available."
fi
if command -v llvm-config-${LLVM_VERSION} &> /dev/null; then
    echo "LLVM config tool is available."
else
    echo "LLVM config tool is not available."
fi
if command -v mlir-opt-${LLVM_VERSION} &> /dev/null; then
    echo "MLIR opt tool is available."
else
    echo "MLIR opt tool is not available."
fi
