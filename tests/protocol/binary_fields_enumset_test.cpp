#include "src/binary_fields.hpp"

#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

#include "protocol/framing.hpp"

namespace {

using Fortran::parser::OmpDirectiveSpecification;
using flang_dumper::binary::FieldEncoder;
using flang_dumper::binary::NodeName;
using flang_dumper::protocol::BinaryContext;
using flang_dumper::protocol::ReadHeader;
using flang_dumper::protocol::ReadRecord;
using flang_dumper::protocol::StreamRecord;

void Check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

void TestNonemptyFlagsAreScalarValues() {
  int owner = 0;
  auto owned_output = std::make_unique<std::ostringstream>(std::ios::binary);
  auto* captured_output = owned_output.get();
  BinaryContext context(std::move(owned_output));

  OmpDirectiveSpecification::Flags flags{
      OmpDirectiveSpecification::Flag::DeprecatedSyntax,
      OmpDirectiveSpecification::Flag::CrossesLabelDo};
  context.Reserve(&owner);
  context.Freeze();
  context.BeginNode(&owner, 1, "OmpDirectiveSpecification");

  FieldEncoder fields{context};
  fields.Dump(flags, NodeName(flags));

  context.EndNode();
  context.Finish();

  std::istringstream input(captured_output->str(), std::ios::binary);
  ReadHeader(input);
  StreamRecord record;
  Check(ReadRecord(input, record) && record.has_node(),
        "expected one node carrying the EnumSet field");
  const auto node = record.node();
  Check(!ReadRecord(input, record), "expected only one node record");

  const auto& attributes = node.attributes();
  Check(attributes.size() == 1, "EnumSet should produce exactly one field");
  Check(attributes[0].key() ==
            "Flags = {DeprecatedSyntax, CrossesLabelDo}",
        "EnumSet should preserve Flang's effective property name");
  Check(attributes[0].value().has_string_value() &&
            attributes[0].value().string_value() ==
                "DeprecatedSyntax, CrossesLabelDo",
        "EnumSet members should be emitted as a scalar string value");
}

}  // namespace

int main() {
  try {
    TestNonemptyFlagsAreScalarValues();
    std::cout << "binary_fields_enumset_test: all checks passed\n";
  } catch (const std::exception& error) {
    std::cerr << "binary_fields_enumset_test: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
