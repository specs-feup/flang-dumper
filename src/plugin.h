#ifndef __PLUGIN_H__
#define __PLUGIN_H__

#include <optional>
#include <string>
#include <variant>

#include "flang/Common/indirection.h"
#include "flang/Parser/parse-tree.h"

#include "collector.h"

template <typename T>
const char *getNodeName(const T &v);
template <typename T>
const char *getNodeName(const std::optional<T> &v);
template <typename T>
const char *getNodeName(const Fortran::common::Indirection<T> &v);
template <typename T>
const char *getNodeName(const std::list<T> &v);

template <typename T>
std::string &getId(const T &v, const char *name);
template <typename T>
std::string getId(const T &v);
template <typename T>
std::string getId(const std::optional<T> &v);
template <typename T>
std::string getId(const Fortran::common::Indirection<T> &v);
template <>
std::string getId(const std::nullopt_t &);

template <typename T>
void dump(const T &v, const char *property_name);
void dump(const char *v, const char *property_name);
std::string escape_cpp_string(const char *input);

void dump(const bool v, const char *property_name);
void dump(std::string_view v, const char *property_name);
std::string escape_quotes(std::string_view sv);

template <>
void dump(const std::uint64_t &v, const char *property_name);
template <>
void dump(const std::string &v, const char *property_name);
template <>
void dump(const Fortran::parser::CharBlock &v, const char *property_name);
template <>
void dump(const std::nullopt_t &v, const char *property_name);
template <typename T>
void dump(const std::list<T> &v, const char *property_name);
template <typename T>
void dump(const Fortran::parser::Statement<T> &v, const char *property_name);
template <typename T>
void dump(const Fortran::parser::Statement<T> &v);
template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v,
          const char *property_name);
template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v);
template <typename... T>
void dump(const std::variant<T...> &v, const char *property_name = "value");
template <typename T>
void dump(const Fortran::common::Indirection<T> &v, const char *property_name);
template <typename T>
void dump(const Fortran::common::Indirection<T> &v);
template <typename T>
void dump(const std::optional<T> &v, const char *property_name);
template <typename... T>
void dump(const std::tuple<T...> &v);
void dump(const Fortran::parser::Expr &v);

template <typename T>
void dumpWrapper(const T &v)
{
  dump(v.v, getNodeName(v.v));
}

template <typename T>
void dumpUnion(const T &v) { dump(v.u); }

template <typename T>
void dumpTuple(const T &v) { dump(v.t); }

template <typename T>
void dumpConstraint(const T &v) { dump(v.thing); }

#define DUMP_PROPERTY(KEY, VALUE) \
  llvm::outs() << ",\n\"" << KEY << "\": \"" << VALUE << "\"";

#define DUMP_BARE_NODE(CONTENT)                                 \
  if (!firstNodeDump)                                           \
  {                                                             \
    llvm::outs() << ",\n";                                      \
  }                                                             \
  else                                                          \
  {                                                             \
    firstNodeDump = false;                                      \
  }                                                             \
  llvm::outs() << "{\n";                                        \
  llvm::outs() << "\"" << "id" << "\": \"" << getId(v) << "\""; \
  CONTENT;                                                      \
  llvm::outs() << "\n}";                                        \
  return true;

#define DUMP_NODE(CLASS, CONTENTS)                                  \
  bool Pre(const CLASS &v)                                          \
  {                                                                 \
    DUMP_BARE_NODE({                                                \
      if constexpr (UnionTrait<CLASS>)                              \
      {                                                             \
        dumpUnion(v);                                               \
      }                                                             \
      else if constexpr (TupleTrait<CLASS>)                         \
      {                                                             \
        dumpTuple(v);                                               \
      }                                                             \
      else if constexpr (WrapperTrait<CLASS>)                       \
      {                                                             \
        dumpWrapper(v);                                             \
      }                                                             \
      else if constexpr (ConstraintTrait<CLASS>)                    \
      {                                                             \
        dumpConstraint(v);                                          \
      }                                                             \
      else                                                          \
      {                                                             \
        llvm::errs() << "Not implemented for " << getId(v) << "\n"; \
      }                                                             \
                                                                    \
      CONTENTS;                                                     \
    })                                                              \
  }

#define CONCATENATE_(X, Y) X##Y
#define CONCATENATE(X, Y) CONCATENATE_(X, Y)
#define STRINGIFY_DETAIL(x) #x
#define STRINGIFY(x) STRINGIFY_DETAIL(x)

// Macro to register and dump enum values using ENUM_CLASS utilities
#define DUMP_ENUM_HELPER(Namespace, EnumType, EnumNumber)                   \
  static void CONCATENATE(dump_, EnumNumber)()                              \
  {                                                                         \
    llvm::outs() << "[";                                                    \
    for (std::size_t i = 0; i < Namespace::EnumType##_enumSize; ++i)        \
    {                                                                       \
      if (i > 0)                                                            \
      {                                                                     \
        llvm::outs() << ", ";                                               \
      }                                                                     \
      llvm::outs() << "\""                                                  \
                   << Namespace::EnumToString(                              \
                          static_cast<Namespace::EnumType>(i))              \
                   << "\"";                                                 \
    }                                                                       \
    llvm::outs() << "]";                                                    \
  }                                                                         \
  struct CONCATENATE(RegisterEnum_, EnumNumber)                             \
  {                                                                         \
    CONCATENATE(RegisterEnum_, EnumNumber)()                                \
    {                                                                       \
      Collector<ThisClass>::Registrar reg{STRINGIFY(Namespace::EnumType),   \
                                          &CONCATENATE(dump_, EnumNumber)}; \
    }                                                                       \
  } CONCATENATE(registerEnum_, EnumNumber);                                 \
  DUMP_NODE(Namespace::EnumType, {                                          \
    dump(STRINGIFY(Namespace::EnumType), "disambiguation");                 \
    dump(Namespace::EnumToString(v), "value");                              \
  })

#define DUMP_ENUM(Namespace, EnumType) \
  DUMP_ENUM_HELPER(Namespace, EnumType, __COUNTER__)

#endif // __PLUGIN_H__
