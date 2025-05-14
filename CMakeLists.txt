cmake_minimum_required(VERSION 3.14)
project(FlangAstDumper)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

set(FLANG_VERSION 20)

add_compile_options(-Wsuggest-override)
set(CC clang-${FLANG_VERSION})
set(CXX clang++-${FLANG_VERSION})
set(CMAKE_C_COMPILER ${CC})
set(CMAKE_CXX_COMPILER ${CXX})
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

SET(LLVM_DIR "/usr/lib/llvm-${FLANG_VERSION}/cmake")
SET(MLIR_DIR "/usr/lib/llvm-${FLANG_VERSION}/lib/cmake/mlir")
SET(Clang_DIR "/usr/lib/llvm-${FLANG_VERSION}/lib/cmake/clang")
SET(Flang_DIR "/usr/lib/llvm-${FLANG_VERSION}/lib/cmake/flang")
find_package(LLVM REQUIRED CONFIG)
find_package(MLIR REQUIRED CONFIG)
find_package(Clang REQUIRED CONFIG)
find_package(Flang REQUIRED CONFIG)

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")

# Set the LLVM and Flang include directories
include_directories(${LLVM_INCLUDE_DIRS})
include_directories(${MLIR_INCLUDE_DIRS})
include_directories(${CLANG_INCLUDE_DIRS})
include_directories(${FLANG_INCLUDE_DIRS})

# Add definitions needed for LLVM and Flang
add_definitions(${LLVM_DEFINITIONS})
add_definitions(${MLIR_DEFINITIONS})
add_definitions(${Clang_DEFINITIONS})
add_definitions(${Flang_DEFINITIONS})


# Set Endianess flag for Flang
include(TestBigEndian)

test_big_endian(IS_BIG_ENDIAN)

if(IS_BIG_ENDIAN)
    add_definitions(-DFLANG_BIG_ENDIAN)
    message(STATUS "System is big endian")
else()
    add_definitions(-DFLANG_LITTLE_ENDIAN)
    message(STATUS "System is little endian")
endif()



#file (GLOB ENUM_FILES CONFIGURE_DEPENDS
#    "src/FlangEnums/enums_*.h"
#    "src/FlangEnums/enums_*.cpp")

#set(SOURCE_FILES
#    src/Clang/ClangAst.cpp
#    src/Clang/ClangNodes.cpp
#    src/ClangEnums/ClangEnums.cpp
#    src/TypeMarker/TypeMarker.cpp
#    src/Clava/ClavaConstants.cpp
#    src/Clava/ClavaDecl.cpp
#    src/ClavaDataDumper/ClavaDataDumper.cpp
#    src/ClavaDataDumper/ClavaDataDumperAttrs.cpp
#    src/ClavaDataDumper/ClavaDataDumperDecls.cpp
#    src/ClavaDataDumper/ClavaDataDumperStmts.cpp
#    src/ClavaDataDumper/ClavaDataDumperTypes.cpp
#    src/ChildrenVisitor/ChildrenVisitorAttrs.cpp
#    src/ChildrenVisitor/ChildrenVisitorDecls.cpp
#    src/ChildrenVisitor/ChildrenVisitorExtras.cpp
#    src/ChildrenVisitor/ChildrenVisitorStmts.cpp
#    src/ChildrenVisitor/ChildrenVisitorTypes.cpp
#    src/ClangAstDumper/ClangAstDumper.cpp
#    src/ClangAstDumper/ClangAstDumperAttr.cpp
#    src/ClangAstDumper/ClangAstDumperDecls.cpp
#    src/ClangAstDumper/ClangAstDumperExprs.cpp
#    src/ClangAstDumper/ClangAstDumperExtra.cpp
#    src/ClangAstDumper/ClangAstDumperStmts.cpp
#    src/ClangAstDumper/ClangAstDumperTypes.cpp
#    ${ENUM_FILES}
#    )
#
#add_custom_target (
#    flang_enums
#    COMMAND node flang_enums/Main.mjs ${LLVM_DIR} src/	
#    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR})

# Build plugin
#add_library(plugin MODULE ${SOURCE_FILES} src/plugin.cpp)

add_library(DumpASTPlugin MODULE src/plugin.cpp)

# Avoid lib prefix so that Flang finds the plugin as `DumpParseTreePlugin.so`, not `libDumpParseTreePlugin.so`
set_target_properties(DumpASTPlugin PROPERTIES PREFIX "")
target_compile_features(DumpASTPlugin PRIVATE)

#add_dependencies(plugin flang_enums)

# Build tool
#add_executable(tool ${SOURCE_FILES} src/tool.cpp)
#target_compile_features(tool PRIVATE)
#add_dependencies(tool flang_enums)
#
#message(STATUS "SYSTEM PROCESSOR: '${CMAKE_SYSTEM_PROCESSOR}'")
#if(${CMAKE_SYSTEM_PROCESSOR} MATCHES "arm") 
#    set(PROCESSOR_PREFIX "ARM")
#else()
#    set(PROCESSOR_PREFIX "X86")
#endif()
