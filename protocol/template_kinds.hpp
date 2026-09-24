#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace flang_dumper {

// Represents all instantiations of the Fortran::parser::Statement wrapper
// template.
inline constexpr std::uint32_t kStatementTemplateKindId = 1000001U;
// Represents all instantiations of the
// Fortran::parser::UnlabeledStatement wrapper template.
inline constexpr std::uint32_t kUnlabeledStatementTemplateKindId = 1000002U;

struct TemplateKindInfo {
  std::uint32_t id;
  std::string_view cpp_type;
  std::string_view kind_name;
};

inline constexpr TemplateKindInfo kTemplateKinds[] = {
    {kStatementTemplateKindId, "Fortran::parser::Statement", "Statement"},
    {kUnlabeledStatementTemplateKindId,
     "Fortran::parser::UnlabeledStatement",
     "UnlabeledStatement"},
};

inline constexpr std::size_t kTemplateKindCount =
    sizeof(kTemplateKinds) / sizeof(kTemplateKinds[0]);

constexpr const TemplateKindInfo* find_template_kind_by_name(
    std::string_view kind_name) noexcept {
  for (const auto& kind : kTemplateKinds) {
    if (kind.kind_name == kind_name) {
      return &kind;
    }
  }
  return nullptr;
}

}  // namespace flang_dumper
