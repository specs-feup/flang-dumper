#ifndef __PLUGIN_H__
#define __PLUGIN_H__

#include <optional>
#include <sstream>
#include <string>
#include <type_traits>
#include <variant>

#include "flang/Common/indirection.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"

#define DUMP_FIRST_PROPERTY(KEY, VALUE)                                              \
  llvm::outs() << "\"" << KEY << "\": \"" << VALUE << "\"";

template <typename T, template <typename...> class Template>
struct is_specialization : std::false_type {};

template <typename... Args, template <typename...> class Template>
struct is_specialization<Template<Args...>, Template> : std::true_type {};

template <typename T> struct is_indirection : std::false_type {};

template <typename T, bool COPY>
struct is_indirection<Fortran::common::Indirection<T, COPY>> : std::true_type {
};

template <typename T> const char *getNodeName(const T &v) {
  if constexpr (is_specialization<T, Fortran::parser::Statement>::value) {
    return "Statement";
  } else if constexpr (is_specialization<
                           T, Fortran::parser::UnlabeledStatement>::value) {
    return "UnlabeledStatement";
  } else if constexpr (is_specialization<T, Fortran::parser::Scalar>::value) {
    return "Scalar";
  } else if constexpr (is_specialization<T, Fortran::parser::Constant>::value) {
    return "Constant";
  } else if constexpr (is_specialization<T, Fortran::parser::Integer>::value) {
    return "Integer";
  } else if constexpr (is_specialization<T, Fortran::parser::Logical>::value) {
    return "Logical";
  } else if constexpr (is_specialization<T,
                                         Fortran::parser::DefaultChar>::value) {
    return "DefaultChar";
  } else if constexpr (std::is_same_v<T, Fortran::parser::CharBlock>) {
    return "CharBlock";
  } else {
    if constexpr (std::is_same_v<
                      decltype(Fortran::parser::ParseTreeDumper::GetNodeName(
                          v)),
                      std::string>) {
      static std::string name =
          Fortran::parser::ParseTreeDumper::GetNodeName(v);
      return name.c_str();
    } else {
      return Fortran::parser::ParseTreeDumper::GetNodeName(v);
    }
  }
}

template <typename T> const char *getNodeName(const std::optional<T> &v) {
  if (v.has_value()) {
    return getNodeName(v.value());
  } else {
    return "null";
  }
}

template <typename T>
const char *getNodeName(const Fortran::common::Indirection<T> &v) {
  return getNodeName(v.value());
}

template <typename T> const char *getNodeName(const std::list<T> &v) {
  if (v.empty()) {
    return "list";
  } else {
    return getNodeName(v.front());
  }
}

template <typename T> std::string &getId(const T &v, const char *name) {
  std::ostringstream oss;
  oss << "0x" << std::hex << reinterpret_cast<uintptr_t>(&v) << "-" << name;
  static std::string id;
  id = oss.str();
  return id;
}

template <typename T> std::string getId(const T &v) {
  return getId(v, getNodeName(v));
}

template <typename T> std::string getId(const std::optional<T> &v) {
  if (v.has_value()) {
    return getId(v.value());
  } else {
    return getId(std::nullopt);
  }
}

template <typename T>
std::string getId(const Fortran::common::Indirection<T> &v) {
  return getId(v.value());
}

template <> inline std::string getId(const std::nullopt_t &) { return "null"; }

#define DUMP_NODE(CLASS, CONTENTS)                                             \
  bool Pre(const CLASS &v) {                                             \
    if(list_first) {                                                            \
        list_first = false;                                                     \
    } else {                                                                    \
        llvm::outs() << ",\n";                                                  \
    }                                                                           \
                                                                               \
    llvm::outs() << "{\n";                                                     \
    DUMP_FIRST_PROPERTY("id", getId(v))                                              \
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
    llvm::outs() << "}";                                                    \
    return true;                                                               \
  }

auto variant_visitor = [](auto &value) {
  llvm::outs() << "\"" << getId(value) << "\"";
};

template <typename T> void dump(const T &v, const char *property_name) {
  llvm::outs() << ",\n\"" << property_name << "\": \"" << getId(v) << "\"";
}

inline void dump(const char *v, const char *property_name) {
  llvm::outs() << ",\n\"" << property_name << "\": \"" << v << "\"";
}

inline void dump(const std::uint64_t v, const char *property_name) {
  llvm::outs() << ",\n\"" << property_name << "\": \"" << v << "\"";
}

template <> inline void dump(const std::string &v, const char *property_name) {
    dump(v.c_str(), property_name);
}


template <>
inline void dump(const Fortran::parser::CharBlock &v,
                 const char *property_name) {
  dump(v.ToString(), property_name);
}

template <>
inline void dump(const std::nullopt_t &v, const char *property_name) {
  if (!strcmp(property_name, "null")) {
    return;
  }

  dump("null", property_name);
}

template <typename T>
void dump(const std::list<T> &v, const char *property_name) {
  if (!strcmp(property_name, "list")) {
    return;
  }

  llvm::outs() << ",\n\"" << property_name << "\": [\n";

  bool first = true;
  for (const auto &item : v) {
      if(first) {
          first = false;
      } else {
          llvm::outs() << ",\n";
      }
    llvm::outs() << "\"" << getId(item) << "\"";
  }
  llvm::outs() << "]";
}

template <typename T>
void dump(const Fortran::parser::Statement<T> &v, const char *property_name) {
  llvm::outs() << ",\n\"" << property_name << "<" << getNodeName(v.statement)
               << ">\": \"" << getId(v) << "\"";
}

template <typename T> void dump(const Fortran::parser::Statement<T> &v) {
  llvm::outs() << ",\n\"" << getNodeName(v) << "<" << getNodeName(v.statement)
               << ">\": \"" << getId(v) << "\"";
}

template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v,
          const char *property_name) {
  llvm::outs() << ",\n\"" << property_name << "<" << getNodeName(v.statement)
               << ">\": \"" << getId(v) << "\"";
}

template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v) {
  llvm::outs() << ",\n\"" << getNodeName(v) << "<" << getNodeName(v.statement)
               << ">\": \"" << getId(v) << "\"";
}

template <typename... T>
void dump(const std::variant<T...> &v, const char *property_name = "value") {
  llvm::outs() << ",\n\"" << property_name << "\": ";
  std::visit(variant_visitor, v);
  llvm::outs() << "";
}

template <typename T>
void dump(const Fortran::common::Indirection<T> &v, const char *property_name) {
  dump(v.value(), property_name);
}

template <typename T>
void dump(const std::optional<T> &v, const char *property_name) {
  if (v.has_value()) {
    dump(v.value(), property_name);
  } else {
    dump(std::nullopt, property_name);
  }
}

template <typename... T> void dump(const std::tuple<T...> &v) {
  // For each element in the tuple, call dump
  std::apply([](const auto &...e) { ((dump(e, getNodeName(e))), ...); }, v);
}

template <typename T> void dumpWrapper(const T &v) {
  dump(v.v, getNodeName(v.v));
}

template <typename T> void dumpUnion(const T &v) { dump(v.u); }

template <typename T> void dumpTuple(const T &v) { dump(v.t); }

template <typename T> void dumpConstraint(const T &v) { dump(v.thing); }

#endif // __PLUGIN_H__
