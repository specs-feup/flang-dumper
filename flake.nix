{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
  };

  outputs = inputs@{ flake-parts, ... }: flake-parts.lib.mkFlake { inherit inputs; } {
    perSystem = { pkgs, ... }: {
      devShells.default = let
        buildScript = pkgs.writeShellApplication {
          name = "build";
          text = ''
            ./scripts/build.sh -- \
              -DLLVM_DIR="$LLVM_HOME/lib/cmake/llvm" \
              -DMLIR_DIR="$LLVM_HOME/lib/cmake/mlir" \
              -DClang_DIR="$LLVM_HOME/lib/cmake/clang" \
              -DFlang_DIR="$LLVM_HOME/lib/cmake/flang"
          '';
        };
        
      in pkgs.mkShell {
        nativeBuildInputs = with pkgs; [ cmake buildScript ];

        shellHook = ''
          export LLVM_HOME="$(realpath ../llvm/install)"
          export PATH="$LLVM_HOME/bin:$PATH"
          export LD_LIBRARY_PATH="$LLVM_HOME/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

          # CMake environment variables
          export LLVM_DIR="$LLVM_HOME/lib/cmake/llvm"
          export MLIR_DIR="$LLVM_HOME/lib/cmake/mlir"
          export Clang_DIR="$LLVM_HOME/lib/cmake/clang"
          export Flang_DIR="$LLVM_HOME/lib/cmake/flang"
          export CC=clang-23
          export CXX=clang-23
        '';
      };
    };

    systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
  };
}