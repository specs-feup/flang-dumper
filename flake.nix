{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    llvm-nix = {
      url = "github:Process-ing/llvm-nix";
      inputs = {
        nixpkgs.follows = "nixpkgs";
        llvm-project.url = "github:llvm/llvm-project/release/22.x";
      };
    };
  };

  outputs = { self, nixpkgs, llvm-nix }: let
    systems = [ "x86_64-linux" "aarch64-linux" ];
    forAllSystems = f: nixpkgs.lib.genAttrs systems f;
  in {
    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
    in {
      default = let
        llvmCmakeDir = "${llvm-nix.packages.${system}.default}/lib/cmake";

        buildScript = pkgs.writeShellApplication {
          name = "build";
          text = ''
            ./scripts/build.sh -- \
              -DLLVM_DIR="${llvmCmakeDir}/llvm" \
              -DMLIR_DIR="${llvmCmakeDir}/mlir" \
              -DClang_DIR="${llvmCmakeDir}/clang" \
              -DFlang_DIR="${llvmCmakeDir}/flang"
          '';
        };
      in pkgs.mkShell {
        nativeBuildInputs = with pkgs; [
          llvm-nix.packages.${system}.default
          cmake
          buildScript
        ];

        # CMake environment variables
        LLVM_DIR = "${llvmCmakeDir}/llvm";
        MLIR_DIR = "${llvmCmakeDir}/mlir";
        Clang_DIR = "${llvmCmakeDir}/clang";
        Flang_DIR = "${llvmCmakeDir}/flang";

        shellHook = ''
          # Enforce Clang as C/C++ compiler
          CC=clang-22
          CXX=clang-22
        '';
      };
    });
  };
}