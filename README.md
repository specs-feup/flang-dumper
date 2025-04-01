# flang-dumper

Dumper of flang's AST into a JSON format.

## Building

```sh
mkdir build
cd build
cmake ..
make
```

The CMakeLists.txt has two targets, `plugin` and `tool`, use `<MAKE_CMD> <target>` to build a specific target.

The target `tool` has been successfully built in Ubuntu, make sure the executable flang-<VERSION> is in the path, as well as the path `/usr/lib/llvm-<VERSION>`.

## Dependencies

**Node.js is required to build this project**

```sh
# Required for all targets
sudo apt install flang-20 libflang-20-dev llvm-20-dev libmlir-20-dev mlir-20-tools
```
