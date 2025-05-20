# flang-dumper

Dumper of flang's AST into a JSON format.

## Installing dependencies

There is a [script](https://github.com/specs-feup/flang-dumper/blob/main/scripts/install-dependencies.sh) for installing the required dependecies.

## Building

```sh
cmake -B build
cd build
make
```

## Dependencies

```sh
# Required for all targets
sudo apt install flang-20 libflang-20-dev llvm-20-dev libmlir-20-dev mlir-20-tools
```

## WSL Support

Flang 20 requires at least Ubuntu 25.04. If this distribuition is not available in WSL, you can follow these steps:

-   Get the [WSL image](https://releases.ubuntu.com/plucky/)
-   Import the downloaded image, e.g., `wsl --import "Ubuntu25.04" <install_path> ubuntu-25.04-wsl-amd64.wsl`
-   You can check if it is installed with `wsl -l -v`
-   Execute the distribution with `wsl -d Ubuntu25.04`
