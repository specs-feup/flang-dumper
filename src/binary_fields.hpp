#ifndef FLANG_DUMPER_BINARY_FIELDS_HPP
#define FLANG_DUMPER_BINARY_FIELDS_HPP

#include <cstdint>
#include <cstring>
#include <list>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <utility>
#include <variant>
#include <vector>

#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Semantics/scope.h"

#include "protocol/binary_context.hpp"

namespace flang_dumper::binary {

template <typename T, template <typename...> class Template>
struct is_specialization : std::false_type {};

template <template <typename...> class Template, typename... Args>
struct is_specialization<Template<Args...>, Template> : std::true_type {};

template <typename T> const char* NodeName(const T& value);
template <typename T> const char* NodeName(const std::optional<T>& value);
template <typename T>
const char* NodeName(const Fortran::common::Indirection<T>& value);
template <typename T> const char* NodeName(const std::list<T>& value);

template <typename T>
const char* NodeName(const T& value) {
  if constexpr (is_specialization<T, Fortran::parser::Statement>::value) {
    return "Statement";
  } else if constexpr (
      is_specialization<T, Fortran::parser::UnlabeledStatement>::value) {
    return "UnlabeledStatement";
  } else if constexpr (
      is_specialization<T, Fortran::parser::Scalar>::value ||
      is_specialization<T, Fortran::parser::Constant>::value ||
      is_specialization<T, Fortran::parser::Integer>::value ||
      is_specialization<T, Fortran::parser::Logical>::value) {
    return "Expr";
  } else if constexpr (
      is_specialization<T, Fortran::parser::DefaultChar>::value) {
    return "DefaultChar";
  } else if constexpr (std::is_same_v<T, Fortran::parser::CharBlock>) {
    return "CharBlock";
  } else if constexpr (
      std::is_same_v<T, Fortran::parser::CommonStmt::Block>) {
    return "CommonStmtBlock";
  } else {
    if constexpr (std::is_same_v<
                      decltype(Fortran::parser::ParseTreeDumper::GetNodeName(
                          value)),
                      std::string>) {
      static std::string name =
          Fortran::parser::ParseTreeDumper::GetNodeName(value);
      return name.c_str();
    } else {
      return Fortran::parser::ParseTreeDumper::GetNodeName(value);
    }
  }
}

template <typename T>
const char* NodeName(const std::optional<T>& value) {
  return value.has_value() ? NodeName(value.value()) : "null";
}

template <typename T>
const char* NodeName(const Fortran::common::Indirection<T>& value) {
  return NodeName(value.value());
}

template <typename T>
const char* NodeName(const std::list<T>& value) {
  return value.empty() ? "list" : NodeName(value.front());
}

template <typename T> const void* IdentityOf(const T& value);
template <typename T> const void* IdentityOf(const std::optional<T>& value);
template <typename T>
const void* IdentityOf(const Fortran::common::Indirection<T>& value);
inline const void* IdentityOf(std::nullopt_t);

template <typename T>
const void* IdentityOf(const T& value) {
  return static_cast<const void*>(std::addressof(value));
}

template <typename T>
const void* IdentityOf(const std::optional<T>& value) {
  return value.has_value() ? IdentityOf(value.value()) : nullptr;
}

template <typename T>
const void* IdentityOf(const Fortran::common::Indirection<T>& value) {
  return IdentityOf(value.value());
}

inline const void* IdentityOf(std::nullopt_t) { return nullptr; }

class FieldEncoder final {
public:
  explicit FieldEncoder(protocol::BinaryContext& context) : context_{context} {}

  template <typename T>
  void Dump(const T& value, const char* key) {
    context_.AddReference(key, IdentityOf(value));
  }

  void Dump(const char* value, const char* key) {
    context_.AddString(key, value ? value : "");
  }

  void Dump(std::string_view value, const char* key) {
    context_.AddString(key, std::string{value});
  }

  void Dump(const std::string& value, const char* key) {
    context_.AddString(key, value);
  }

  void Dump(bool value, const char* key) { context_.AddBool(key, value); }

  void Dump(int value, const char* key) {
    context_.AddInteger(key, static_cast<std::int64_t>(value));
  }

  void Dump(std::int64_t value, const char* key) {
    context_.AddInteger(key, value);
  }

  void Dump(std::uint64_t value, const char* key) {
    context_.AddUnsigned(key, value);
  }

  void Dump(const Fortran::parser::CharBlock& value, const char* key) {
    Dump(value.ToString(), key);
  }

  void Dump(std::nullopt_t, const char*) {}

  template <typename T>
  void Dump(const std::optional<T>& value, const char* key) {
    if (value.has_value()) {
      Dump(value.value(), key);
    }
  }

  template <typename T>
  void Dump(const std::list<T>& value, const char* key) {
    if (std::strcmp(key, "list") == 0) {
      return;
    }

    std::vector<const void*> identities;
    identities.reserve(value.size());
    for (const auto& item : value) {
      identities.push_back(IdentityOf(item));
    }
    context_.AddReferenceList(key, identities);
  }

  template <typename T>
  void Dump(const Fortran::parser::Scalar<T>& value, const char* key) {
    Dump(value.thing, key);
  }

  template <typename T>
  void Dump(const Fortran::parser::Logical<T>& value, const char* key) {
    Dump(value.thing, key);
  }

  template <typename T>
  void Dump(const Fortran::parser::Integer<T>& value, const char* key) {
    Dump(value.thing, key);
  }

  template <typename T>
  void Dump(const Fortran::parser::Constant<T>& value, const char* key) {
    Dump(value.thing, key);
  }

  template <typename T>
  void Dump(const Fortran::parser::DefaultChar<T>& value, const char* key) {
    Dump(value.thing, key);
  }

  void Dump(Fortran::parser::Sign value, const char* key) {
    switch (value) {
    case Fortran::parser::Sign::Positive:
      Dump("positive", key);
      break;
    case Fortran::parser::Sign::Negative:
      Dump("negative", key);
      break;
    }
  }

  void Dump(const Fortran::semantics::Scope& scope, const char* key) {
    Dump(Fortran::semantics::Scope::EnumToString(scope.kind()), key);
  }

  template <typename T>
  void Dump(const Fortran::parser::Statement<T>& value, const char* key) {
    context_.AddReference(StatementKey(key, NodeName(value.statement)),
                          IdentityOf(value));
  }

  template <typename T>
  void Dump(const Fortran::parser::Statement<T>& value) {
    context_.AddReference(StatementKey(NodeName(value), NodeName(value.statement)),
                          IdentityOf(value));
  }

  template <typename T>
  void Dump(const Fortran::parser::UnlabeledStatement<T>& value,
            const char* key) {
    context_.AddReference(StatementKey(key, NodeName(value.statement)),
                          IdentityOf(value));
  }

  template <typename T>
  void Dump(const Fortran::parser::UnlabeledStatement<T>& value) {
    context_.AddReference(
        StatementKey(NodeName(value), NodeName(value.statement)),
        IdentityOf(value));
  }

  template <typename... T>
  void Dump(const std::variant<T...>& value, const char*) {
    DumpVariant(value);
  }

  template <typename... T>
  void Dump(const std::variant<T...>& value) {
    DumpVariant(value);
  }

  template <typename T>
  void Dump(const Fortran::common::Indirection<T>& value, const char* key) {
    Dump(value.value(), key);
  }

  template <typename T>
  void Dump(const Fortran::common::Indirection<T>& value) {
    Dump(value.value());
  }

  void Dump(const Fortran::parser::Expr& value) { Dump(value.u); }

  template <typename... T>
  void Dump(const std::tuple<T...>& value) {
    std::apply(
        [this](const auto&... items) { (Dump(items, NodeName(items)), ...); },
        value);
  }

private:
  static std::string StatementKey(const char* property,
                                  const char* statement_name) {
    std::string key{property};
    key += '<';
    key += statement_name;
    key += '>';
    return key;
  }

  template <typename... T>
  void DumpVariant(const std::variant<T...>& value) {
    std::visit(
        [this](const auto& active) {
          const char* name = NodeName(active);
          Dump(name, "variantKey");
          Dump(active, name);
        },
        value);
  }

  protocol::BinaryContext& context_;
};

} // namespace flang_dumper::binary

#endif // FLANG_DUMPER_BINARY_FIELDS_HPP
