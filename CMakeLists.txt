cmake_minimum_required(VERSION 3.20)

# The plugin is tightly coupled to the Flang 23 AST/API. Keep this version
# pinned so a mismatched LLVM/Flang installation fails early and clearly.
set(FLANG_VERSION 23)

# Default to Clang 23, but let users override the compiler through the usual
# CMake cache variables or the CC/CXX environment variables.
if(NOT DEFINED CMAKE_C_COMPILER AND NOT DEFINED ENV{CC})
  find_program(_FLANG_DEFAULT_C_COMPILER NAMES clang-${FLANG_VERSION} clang)
  if(_FLANG_DEFAULT_C_COMPILER)
    set(CMAKE_C_COMPILER "${_FLANG_DEFAULT_C_COMPILER}")
  endif()
endif()
if(NOT DEFINED CMAKE_CXX_COMPILER AND NOT DEFINED ENV{CXX})
  find_program(_FLANG_DEFAULT_CXX_COMPILER NAMES clang-${FLANG_VERSION} clang++)
  if(_FLANG_DEFAULT_CXX_COMPILER)
    set(CMAKE_CXX_COMPILER "${_FLANG_DEFAULT_CXX_COMPILER}")
  endif()
endif()

project(FlangAstDumper LANGUAGES C CXX)

set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(CMAKE_CXX_COMPILER_VERSION)
  string(REGEX MATCH "^([0-9]+)" _FLANG_CXX_MAJOR "${CMAKE_CXX_COMPILER_VERSION}")
  if(NOT _FLANG_CXX_MAJOR STREQUAL "${FLANG_VERSION}")
    message(FATAL_ERROR
      "This plugin requires a C++ compiler from LLVM ${FLANG_VERSION}, but "
      "${CMAKE_CXX_COMPILER} reports ${CMAKE_CXX_COMPILER_VERSION}. "
      "Pass -DCMAKE_CXX_COMPILER=/path/to/clang-${FLANG_VERSION} to override.")
  endif()
endif()

# Discover LLVM/MLIR/Clang through their installed CMake packages. The *_DIR
# variables remain normal cache variables, so custom or self-built LLVM trees
# can be selected with -DLLVM_DIR=... etc.
if(NOT LLVM_DIR)
  find_program(LLVM_CONFIG_EXECUTABLE NAMES llvm-config-${FLANG_VERSION}
    llvm-config)
  if(LLVM_CONFIG_EXECUTABLE)
    execute_process(
      COMMAND "${LLVM_CONFIG_EXECUTABLE}" --cmakedir
      OUTPUT_VARIABLE _LLVM_CONFIG_CMAKEDIR
      OUTPUT_STRIP_TRAILING_WHITESPACE)
    if(_LLVM_CONFIG_CMAKEDIR)
      set(LLVM_DIR "${_LLVM_CONFIG_CMAKEDIR}" CACHE PATH
          "Path to LLVMConfig.cmake")
    endif()
  endif()
endif()

find_package(LLVM REQUIRED CONFIG)
if(NOT LLVM_PACKAGE_VERSION)
  set(LLVM_PACKAGE_VERSION "${LLVM_VERSION}")
endif()
string(REGEX MATCH "^([0-9]+)" _FLANG_LLVM_MAJOR "${LLVM_PACKAGE_VERSION}")
if(NOT _FLANG_LLVM_MAJOR STREQUAL "${FLANG_VERSION}")
  message(FATAL_ERROR
    "This plugin requires LLVM/Flang ${FLANG_VERSION}, but found "
    "${LLVM_PACKAGE_VERSION} in ${LLVM_DIR}. Point LLVM_DIR, MLIR_DIR, "
    "Clang_DIR and Flang_DIR at an LLVM ${FLANG_VERSION} installation.")
endif()

# LLVM installs its CMake packages in different layouts:
#   Ubuntu:  /usr/lib/llvm-23/lib/cmake/{llvm,mlir,clang,flang}
#   Fedora:  /usr/lib64/cmake/{llvm,mlir,clang,flang}
#   Ubuntu (legacy): /usr/lib/llvm-23/cmake/LLVMConfig.cmake
# Derive the sibling package directory from the discovered LLVM_DIR so users
# only need to override LLVM_DIR when pointing at a custom build tree.
get_filename_component(_LLVM_CMAKE_PARENT "${LLVM_DIR}" DIRECTORY)
get_filename_component(_LLVM_CMAKE_PARENT_NAME "${_LLVM_CMAKE_PARENT}" NAME)
if(_LLVM_CMAKE_PARENT_NAME STREQUAL "cmake")
  set(_LLVM_PACKAGE_CMAKE_DIR "${_LLVM_CMAKE_PARENT}")
else()
  set(_LLVM_PACKAGE_CMAKE_DIR "${_LLVM_CMAKE_PARENT}/lib/cmake")
endif()

find_package(MLIR REQUIRED CONFIG HINTS "${_LLVM_PACKAGE_CMAKE_DIR}/mlir")
find_package(Clang REQUIRED CONFIG HINTS "${_LLVM_PACKAGE_CMAKE_DIR}/clang")
find_package(Flang CONFIG QUIET HINTS "${_LLVM_PACKAGE_CMAKE_DIR}/flang")

foreach(_version_var MLIR_VERSION MLIR_PACKAGE_VERSION Clang_VERSION
                    CLANG_VERSION Flang_VERSION FLANG_PACKAGE_VERSION)
  if(DEFINED ${_version_var})
    string(REGEX MATCH "^([0-9]+)" _FLANG_PKG_MAJOR "${${_version_var}}")
    if(_FLANG_PKG_MAJOR AND NOT _FLANG_PKG_MAJOR STREQUAL "${FLANG_VERSION}")
      message(FATAL_ERROR
        "${_version_var} is ${${_version_var}}, but this plugin requires "
        "LLVM/Flang ${FLANG_VERSION}.")
    endif()
  endif()
endforeach()

# Some distributions (e.g. Fedora/CentOS) do not install FlangConfig.cmake.
# Fall back to llvm-config plus a header lookup in that case.
set(_FLANG_INCLUDE_HINTS
  ${FLANG_INCLUDE_DIRS}
  ${Flang_INCLUDE_DIRS}
  ${LLVM_INCLUDE_DIRS}
  /usr/include
  /usr/local/include)

find_program(FLANG_LLVM_CONFIG NAMES llvm-config-${FLANG_VERSION} llvm-config
  HINTS ${LLVM_TOOLS_BINARY_DIR})
if(FLANG_LLVM_CONFIG)
  execute_process(
    COMMAND "${FLANG_LLVM_CONFIG}" --includedir
    OUTPUT_VARIABLE _FLANG_LLVM_INCLUDEDIR
    OUTPUT_STRIP_TRAILING_WHITESPACE)
  execute_process(
    COMMAND "${FLANG_LLVM_CONFIG}" --libdir
    OUTPUT_VARIABLE _FLANG_LLVM_LIBDIR
    OUTPUT_STRIP_TRAILING_WHITESPACE)
  list(APPEND _FLANG_INCLUDE_HINTS "${_FLANG_LLVM_INCLUDEDIR}")
  set(FLANG_LIBRARY_DIRS "${_FLANG_LLVM_LIBDIR}" CACHE PATH
      "Flang library directory")
endif()

find_path(FLANG_INCLUDE_DIR
  NAMES flang/Frontend/FrontendActions.h
  HINTS ${_FLANG_INCLUDE_HINTS})
if(NOT FLANG_INCLUDE_DIR)
  message(FATAL_ERROR
    "Flang ${FLANG_VERSION} headers were not found. Install the Flang "
    "development files or pass -DFlang_DIR=... / -DFLANG_INCLUDE_DIR=...")
endif()

if(DEFINED Flang_INCLUDE_DIRS)
  list(APPEND FLANG_INCLUDE_DIRS ${Flang_INCLUDE_DIRS})
endif()
if(DEFINED Clang_INCLUDE_DIRS)
  list(APPEND CLANG_INCLUDE_DIRS ${Clang_INCLUDE_DIRS})
endif()

set(_FLANG_INCLUDE_DIRS
  ${LLVM_INCLUDE_DIRS}
  ${MLIR_INCLUDE_DIRS}
  ${CLANG_INCLUDE_DIRS}
  ${FLANG_INCLUDE_DIRS}
  ${FLANG_INCLUDE_DIR})
list(REMOVE_DUPLICATES _FLANG_INCLUDE_DIRS)

add_library(DumpASTPlugin MODULE src/comments.cpp src/plugin.cpp)

# Avoid the lib prefix so Flang can load the plugin as DumpASTPlugin.so.
set_target_properties(DumpASTPlugin PROPERTIES
  PREFIX ""
  POSITION_INDEPENDENT_CODE ON)

target_compile_features(DumpASTPlugin PRIVATE cxx_std_17)
target_include_directories(DumpASTPlugin SYSTEM PRIVATE ${_FLANG_INCLUDE_DIRS})

foreach(_defs_var LLVM_DEFINITIONS MLIR_DEFINITIONS CLANG_DEFINITIONS
                    FLANG_DEFINITIONS)
  if(DEFINED ${_defs_var})
    separate_arguments(_defs_list NATIVE_COMMAND "${${_defs_var}}")
    foreach(_def IN LISTS _defs_list)
      if(_def MATCHES "^-D(.*)$")
        target_compile_definitions(DumpASTPlugin PRIVATE "${CMAKE_MATCH_1}")
      elseif(_def)
        target_compile_definitions(DumpASTPlugin PRIVATE "${_def}")
      endif()
    endforeach()
  endif()
endforeach()

# Match the LLVM build configuration. Mismatched RTTI/exception settings are a
# common cause of plugin load failures.
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  target_compile_options(DumpASTPlugin PRIVATE -Wsuggest-override)
  if(DEFINED LLVM_ENABLE_RTTI AND NOT LLVM_ENABLE_RTTI)
    target_compile_options(DumpASTPlugin PRIVATE -fno-rtti)
  endif()
  if(DEFINED LLVM_ENABLE_EH AND NOT LLVM_ENABLE_EH)
    target_compile_options(DumpASTPlugin PRIVATE -fno-exceptions)
  endif()
endif()

# Set the endianness flag expected by Flang.
include(TestBigEndian)
test_big_endian(IS_BIG_ENDIAN)
if(IS_BIG_ENDIAN)
  target_compile_definitions(DumpASTPlugin PRIVATE FLANG_BIG_ENDIAN)
  message(STATUS "System is big endian")
else()
  target_compile_definitions(DumpASTPlugin PRIVATE FLANG_LITTLE_ENDIAN)
  message(STATUS "System is little endian")
endif()

# Warn if a Flang executable is present but does not match the required version.
find_program(FLANG_EXECUTABLE NAMES flang-${FLANG_VERSION} flang)
if(FLANG_EXECUTABLE)
  execute_process(
    COMMAND "${FLANG_EXECUTABLE}" --version
    OUTPUT_VARIABLE _FLANG_VERSION_OUTPUT
    ERROR_VARIABLE _FLANG_VERSION_ERROR)
  if(NOT _FLANG_VERSION_OUTPUT MATCHES "flang version ${FLANG_VERSION}\\.")
    message(WARNING
      "Found ${FLANG_EXECUTABLE}, but its version does not look like Flang "
      "${FLANG_VERSION}: ${_FLANG_VERSION_OUTPUT}${_FLANG_VERSION_ERROR}")
  endif()
endif()

message(STATUS "Found LLVM ${LLVM_PACKAGE_VERSION}")
message(STATUS "Using LLVMConfig.cmake in: ${LLVM_DIR}")
message(STATUS "Using Flang headers from: ${FLANG_INCLUDE_DIR}")
