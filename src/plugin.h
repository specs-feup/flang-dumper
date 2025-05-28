#ifndef __PLUGIN_H__
#define __PLUGIN_H__

#include <optional>
#include <string>
#include <variant>

#include "flang/Common/indirection.h"
#include "flang/Parser/parse-tree.h"

template <typename T> const char *getNodeName(const T &v);
template <typename T> const char *getNodeName(const std::optional<T> &v);
template <typename T>
const char *getNodeName(const Fortran::common::Indirection<T> &v);
template <typename T> const char *getNodeName(const std::list<T> &v);

template <typename T> std::string &getId(const T &v, const char *name);
template <typename T> std::string getId(const T &v);
template <typename T> std::string getId(const std::optional<T> &v);
template <typename T>
std::string getId(const Fortran::common::Indirection<T> &v);
template <> std::string getId(const std::nullopt_t &);

template <typename T> void dump(const T &v, const char *property_name);
void dump(const char *v, const char *property_name);
void dump(const std::uint64_t v, const char *property_name);
template <> void dump(const std::string &v, const char *property_name);
template <>
void dump(const Fortran::parser::CharBlock &v, const char *property_name);
template <> void dump(const std::nullopt_t &v, const char *property_name);
template <typename T>
void dump(const std::list<T> &v, const char *property_name);
template <typename T>
void dump(const Fortran::parser::Statement<T> &v, const char *property_name);
template <typename T> void dump(const Fortran::parser::Statement<T> &v);
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
void dump(const std::optional<T> &v, const char *property_name);
template <typename... T> void dump(const std::tuple<T...> &v);

template <typename T> void dumpWrapper(const T &v) {
  dump(v.v, getNodeName(v.v));
}

template <typename T> void dumpUnion(const T &v) { dump(v.u); }

template <typename T> void dumpTuple(const T &v) { dump(v.t); }

template <typename T> void dumpConstraint(const T &v) { dump(v.thing); }

#define DUMP_PROPERTY(KEY, VALUE)                                              \
  llvm::outs() << "\"" << KEY << "\": \"" << VALUE << "\",\n";

#define DUMP_NODE(CLASS, CONTENTS)                                             \
  bool Pre(const CLASS &v) const {                                             \
    llvm::outs() << "{\n";                                                     \
    DUMP_PROPERTY("id", getId(v))                                              \
                                                                               \
    if constexpr (UnionTrait<CLASS>) {                                         \
      dumpUnion(v);                                                            \
    } else if constexpr (TupleTrait<CLASS>) {                                  \
      dumpTuple(v);                                                            \
    } else if constexpr (WrapperTrait<CLASS>) {                                \
      dumpWrapper(v);                                                          \
    } else if constexpr (ConstraintTrait<CLASS>) {                             \
      dumpConstraint(v);                                                       \
    }                                                                          \
                                                                               \
    CONTENTS;                                                                  \
                                                                               \
    llvm::outs() << "},\n";                                                    \
    return true;                                                               \
  }

#endif // __PLUGIN_H__
