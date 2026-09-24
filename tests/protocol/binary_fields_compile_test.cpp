#include "src/binary_fields.hpp"

#include <cstdint>
#include <list>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <tuple>
#include <variant>

namespace {

using Fortran::parser::CharBlock;
using Fortran::parser::ContinueStmt;
using Fortran::parser::Name;
using Fortran::parser::Statement;
using Fortran::parser::UnlabeledStatement;
using TestIndirection = Fortran::common::Indirection<Name>;
using TestVariant = std::variant<Name, ContinueStmt>;
using TestTuple = std::tuple<CharBlock, std::optional<Name>>;
constexpr std::uint64_t kMaximumUnsigned =
    std::numeric_limits<std::uint64_t>::max();
static_assert(kMaximumUnsigned == UINT64_MAX,
              "uint64_t encoder test must cover the full unsigned range");

// This function is intentionally never executed. Its body forces the
// FieldEncoder templates used by the binary visitor through the compiler.
void InstantiateFieldEncoder(flang_dumper::protocol::BinaryContext& context,
                             const char* c_string,
                             const std::string& string,
                             std::string_view string_view,
                             bool boolean, int integer,
                             std::int64_t signed_integer,
                             std::uint64_t unsigned_integer,
                             const CharBlock& char_block,
                             const std::optional<Name>& optional,
                             const std::list<Name>& list,
                             const TestIndirection& indirection,
                             const TestVariant& variant,
                             const TestTuple& tuple,
                             const Fortran::parser::Expr& expression,
                             const Statement<ContinueStmt>& statement,
                             const UnlabeledStatement<ContinueStmt>&
                                 unlabeled_statement,
                             const Fortran::parser::Scalar<int>& scalar,
                             const Fortran::parser::Logical<int>& logical,
                             const Fortran::parser::Integer<int>& wrapped_integer,
                             const Fortran::parser::Constant<int>& constant,
                             const Fortran::parser::DefaultChar<std::string>&
                                 default_char,
                             Fortran::parser::Sign sign,
                             const Fortran::semantics::Scope& scope,
                             const Fortran::parser::CommonStmt::Block& block) {
  flang_dumper::binary::FieldEncoder encoder{context};
  encoder.Dump(c_string, "c_string");
  encoder.Dump(string, "string");
  encoder.Dump(string_view, "string_view");
  encoder.Dump(boolean, "boolean");
  encoder.Dump(integer, "integer");
  encoder.Dump(signed_integer, "signed_integer");
  encoder.Dump(unsigned_integer, "unsigned_integer");
  encoder.Dump(kMaximumUnsigned, "maximum_unsigned");
  encoder.Dump(char_block, "char_block");
  encoder.Dump(optional, "optional");
  encoder.Dump(list, "items");
  encoder.Dump(list, "list");
  encoder.Dump(indirection, "indirection");
  encoder.Dump(variant, "choice");
  encoder.Dump(tuple);
  encoder.Dump(expression);
  encoder.Dump(statement, "statement");
  encoder.Dump(statement);
  encoder.Dump(unlabeled_statement, "unlabeled_statement");
  encoder.Dump(unlabeled_statement);
  encoder.Dump(scalar, "scalar");
  encoder.Dump(logical, "logical");
  encoder.Dump(wrapped_integer, "wrapped_integer");
  encoder.Dump(constant, "constant");
  encoder.Dump(default_char, "default_char");
  encoder.Dump(sign, "sign");
  encoder.Dump(scope, "scope");
  encoder.Dump(block, "block");

  (void)flang_dumper::binary::NodeName(statement);
  (void)flang_dumper::binary::NodeName(unlabeled_statement);
  (void)flang_dumper::binary::NodeName(scalar);
  (void)flang_dumper::binary::NodeName(default_char);
  (void)flang_dumper::binary::NodeName(char_block);
  (void)flang_dumper::binary::NodeName(block);
  (void)flang_dumper::binary::NodeName(optional);
  (void)flang_dumper::binary::NodeName(indirection);
  (void)flang_dumper::binary::NodeName(list);
  (void)flang_dumper::binary::IdentityOf(statement);
  (void)flang_dumper::binary::IdentityOf(optional);
  (void)flang_dumper::binary::IdentityOf(indirection);
  (void)flang_dumper::binary::IdentityOf(list);
  (void)flang_dumper::binary::IdentityOf(std::nullopt);
}

} // namespace
