# flang-dumper

Dumper of Flang's AST into a JSON format.

## Requirements

- LLVM/Flang **22** (the plugin is version-locked to the Flang 22 API)
- Clang/Clang++ 22
- CMake 3.20 or newer
- A C++17 compiler

The build defaults to `clang-22`/`clang++-22` when they are available and
falls back to `clang`/`clang++`. You can always override the compiler:

```sh
cmake -B build \
  -DCMAKE_C_COMPILER=/path/to/clang-22 \
  -DCMAKE_CXX_COMPILER=/path/to/clang++-22
```

## Installing dependencies

The dependency script installs the required packages on Debian/Ubuntu only.

```sh
sudo ./scripts/install-dependencies.sh
```

Use `--dry-run` to print the package-manager commands without executing them:

```sh
./scripts/install-dependencies.sh --dry-run
```

The script installs LLVM/Flang 22 and checks that the expected packages and
tools are available.

For Fedora, CentOS Stream/RHEL, and openSUSE, install or build LLVM/Flang 22
manually. Fedora and CentOS Stream currently do not package the Flang C++
headers needed to build a plugin, so a self-built LLVM is usually required
there.

### Arch Linux

Flang 22 is provided through the AUR. Install the LLVM/Flang 22 packages from
the AUR manually, then build with CMake as described below. The dependency
script intentionally does not automate Arch.
```

## Building

```sh
cmake -B build
cmake --build build --parallel
```

Or use the helper script:

```sh
./scripts/build.sh
```

By default, `build.sh` copies `DumpASTPlugin.so` to `/tmp/metafor_$USER/`.
Use `--no-copy` to skip that step:

```sh
./scripts/build.sh --no-copy
```

Extra arguments are passed to CMake; use `--` to separate them:

```sh
./scripts/build.sh -- -DLLVM_DIR=/opt/llvm/lib/cmake/llvm
```

### CMake presets

Presets are provided for common distributions and for a custom LLVM tree:

```sh
cmake --preset ubuntu
cmake --build --preset ubuntu

cmake --preset fedora
cmake --build --preset fedora

cmake --preset centos
cmake --build --preset centos

cmake --preset custom-llvm
cmake --build --preset custom-llvm
```

For the `custom-llvm` preset, set the `LLVM_DIR`, `MLIR_DIR`, `Clang_DIR`, and
`Flang_DIR` environment variables before configuring.

### Building against a self-compiled LLVM

If LLVM/Flang was built by you rather than installed by the distribution, point
CMake at the build tree or install tree:

```sh
cmake -B build \
  -DLLVM_DIR=/path/to/llvm-build/lib/cmake/llvm \
  -DMLIR_DIR=/path/to/llvm-build/lib/cmake/mlir \
  -DClang_DIR=/path/to/llvm-build/lib/cmake/clang \
  -DFlang_DIR=/path/to/llvm-build/lib/cmake/flang
```

Some distributions do not install `FlangConfig.cmake`. In that case the build
falls back to `llvm-config` and a header search. If the headers are in a
non-standard location, pass them explicitly:

```sh
cmake -B build -DFLANG_INCLUDE_DIR=/path/to/flang/include
```

## Running the plugin

```sh
flang-22 -fc1 -load ./build/DumpASTPlugin.so -plugin dump-ast file.f90
```

## WSL support

The Ubuntu package path uses the LLVM 22 packages from apt.llvm.org. If a
recent enough Ubuntu distribution is not available in WSL, you can follow these
steps:

- Get the [WSL image](https://releases.ubuntu.com/plucky/)
- Import the downloaded image, e.g.:
  `wsl --import "Ubuntu25.04" <install_path> ubuntu-25.04-wsl-amd64.wsl`
- You can check if it is installed with `wsl -l -v`
- Execute the distribution with `wsl -d Ubuntu25.04`
