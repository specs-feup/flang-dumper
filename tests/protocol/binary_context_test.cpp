#include "protocol/binary_context.hpp"

#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "protocol/framing.hpp"

namespace {

using flang_dumper::protocol::BinaryContext;
using flang_dumper::protocol::EnumEntry;
using flang_dumper::protocol::ReadHeader;
using flang_dumper::protocol::ReadRecord;
using flang_dumper::protocol::StreamRecord;

void Check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Exception, typename Function>
void ExpectThrows(Function&& function, const std::string& test_name) {
  try {
    function();
  } catch (const Exception&) {
    return;
  }
  throw std::runtime_error(test_name + ": expected exception");
}

void ReadAllNodes(const std::string& bytes, std::vector<StreamRecord>& records) {
  std::istringstream input(bytes, std::ios::binary);
  ReadHeader(input);
  StreamRecord record;
  while (ReadRecord(input, record)) {
    records.push_back(record);
  }
}

void TestPrewalkAndEmission() {
  int parent = 0;
  int child = 0;
  auto owned_output = std::make_unique<std::ostringstream>(std::ios::binary);
  auto* captured_output = owned_output.get();
  BinaryContext context(std::move(owned_output));

  context.Reserve(&parent);
  context.Reserve(&child);
  context.Reserve(&parent);
  context.Freeze();

  context.BeginNode(&parent, 11, "Parent");
  context.AddReference("child", &child);
  context.AddString("same", "first");
  context.AddInteger("same", -42);
  context.AddBool("enabled", true);
  context.AddDouble("ratio", 1.5);
  context.AddBytes("bytes", std::string("\0\xff", 2));
  context.AddReferenceList("children", {&child});
  context.AddReferenceList("empty", {});
  context.AddNull("nothing");
  context.EndNode();

  context.BeginNode(&child, 12, "Child");
  context.AddString("name", "leaf");
  context.EndNode();

  context.WriteComment("parent comment", &parent, true);
  std::vector<EnumEntry> entries(2);
  entries[0].set_name("First");
  entries[0].set_number(0);
  entries[1].set_name("Second");
  entries[1].set_number(-3);
  context.WriteEnumCatalog("ExampleEnum", entries);
  context.Finish();

  std::vector<StreamRecord> records;
  ReadAllNodes(captured_output->str(), records);
  Check(records.size() == 4 && records[0].has_node() &&
            records[1].has_node() && records[2].has_comment() &&
            records[3].has_enum_catalog(),
        "node, comment, and catalog records should be emitted in order");
  const auto& parent_node = records[0].node();
  Check(parent_node.node_id() == 1 && parent_node.kind_id() == 11 &&
            parent_node.kind_name() == "Parent",
        "parent must retain its reserved identity and kind");
  const auto& attributes = parent_node.attributes();
  Check(attributes.size() == 9, "all parent attributes should be retained");
  Check(attributes[0].key() == "child" &&
            attributes[0].value().node_reference() == 2,
        "forward reference should use the child's reserved ID");
  Check(attributes[1].key() == "same" &&
            attributes[1].value().string_value() == "first" &&
            attributes[2].key() == "same" &&
            attributes[2].value().integer_value() == -42,
        "duplicate attribute keys should retain insertion order and values");
  Check(attributes[3].value().bool_value() &&
            attributes[4].value().double_value() == 1.5 &&
            attributes[5].value().bytes_value() == std::string("\0\xff", 2),
        "scalar values and binary data should round-trip");
  Check(attributes[6].key() == "children" &&
            attributes[6].value().list_value().items_size() == 1 &&
            attributes[6].value().list_value().items(0).node_reference() == 2,
        "reference list should contain the reserved child ID");
  Check(attributes[7].key() == "empty" &&
            attributes[7].value().has_list_value() &&
            attributes[7].value().list_value().items().empty(),
        "empty reference list should remain present");
  Check(attributes[8].key() == "nothing" &&
            attributes[8].value().has_null_value(),
        "null value should remain present");
  for (const auto& attribute : attributes) {
    Check(attribute.key() != "absent",
          "an attribute that was never added should remain absent");
  }
  Check(records[1].node().node_id() == 2 &&
            records[1].node().attributes_size() == 1 &&
            records[1].node().attributes(0).key() == "name",
        "child record should follow its parent in reserved order");
  Check(records[2].comment().text() == "parent comment" &&
            records[2].comment().stmt_node_id() == 1 &&
            records[2].comment().trailing(),
        "comment should resolve its statement identity and round-trip");
  Check(records[3].enum_catalog().enum_type_name() == "ExampleEnum" &&
            records[3].enum_catalog().entries_size() == 2 &&
            records[3].enum_catalog().entries(1).name() == "Second" &&
            records[3].enum_catalog().entries(1).number() == -3,
        "enum catalog should round-trip after all nodes");
}

void TestPhaseAndAttributeErrors() {
  int known = 0;
  int unknown = 0;
  auto output = std::make_unique<std::ostringstream>(std::ios::binary);
  BinaryContext context(std::move(output));

  ExpectThrows<std::logic_error>([&] { context.BeginNode(&known, 1, "Known"); },
                                 "begin before freeze");
  ExpectThrows<std::logic_error>([&] { context.AddString("key", "value"); },
                                 "attribute before freeze");
  ExpectThrows<std::logic_error>([&] { context.Finish(); },
                                 "finish before freeze");
  ExpectThrows<std::invalid_argument>([&] { context.Reserve(nullptr); },
                                      "null reservation");
  context.Reserve(&known);
  context.Freeze();
  ExpectThrows<std::logic_error>([&] { context.Freeze(); }, "duplicate freeze");
  ExpectThrows<std::logic_error>([&] { context.AddString("key", "value"); },
                                 "attribute without an open node");
  ExpectThrows<std::logic_error>([&] { context.EndNode(); },
                                 "end without an open node");
  ExpectThrows<std::logic_error>([&] { context.Reserve(&unknown); },
                                 "new reservation after freeze");
  ExpectThrows<std::out_of_range>(
      [&] { context.BeginNode(&unknown, 1, "Unknown"); }, "unknown node identity");
  ExpectThrows<std::invalid_argument>(
      [&] { context.BeginNode(&known, 0, "Known"); }, "zero kind ID");
  ExpectThrows<std::invalid_argument>(
      [&] { context.BeginNode(&known, 1, ""); }, "empty kind name");

  context.BeginNode(&known, 1, "Known");
  ExpectThrows<std::logic_error>(
      [&] { context.BeginNode(&known, 1, "Nested"); }, "nested begin");
  ExpectThrows<std::invalid_argument>(
      [&] { context.AddString("", "value"); }, "empty attribute key");
  ExpectThrows<std::out_of_range>(
      [&] { context.AddReference("unknown", &unknown); }, "unknown reference");
  ExpectThrows<std::out_of_range>(
      [&] { context.AddReferenceList("unknown-list", {&known, &unknown}); },
      "unknown reference in list");
  ExpectThrows<std::logic_error>(
      [&] { context.WriteComment("comment while open", &known, false); },
      "comment while a node is open");
  ExpectThrows<std::logic_error>([&] { context.Finish(); }, "finish with open node");
  context.EndNode();
  ExpectThrows<std::out_of_range>(
      [&] { context.WriteComment("unknown target", &unknown, false); },
      "comment with unknown statement identity");
  context.WriteComment("valid target", &known, false);
  context.Finish();
  ExpectThrows<std::logic_error>([&] { context.Finish(); }, "duplicate finish");
  ExpectThrows<std::logic_error>(
      [&] { context.BeginNode(&known, 1, "Known"); }, "begin after finish");
}

void TestEmissionOrderAndMissingNode() {
  int parent = 0;
  int child = 0;
  auto output = std::make_unique<std::ostringstream>(std::ios::binary);
  BinaryContext out_of_order(std::move(output));
  out_of_order.Reserve(&parent);
  out_of_order.Reserve(&child);
  out_of_order.Freeze();
  out_of_order.BeginNode(&child, 2, "Child");
  ExpectThrows<std::logic_error>([&] { out_of_order.EndNode(); },
                                 "out-of-order emission");

  auto missing_output = std::make_unique<std::ostringstream>(std::ios::binary);
  BinaryContext missing(std::move(missing_output));
  missing.Reserve(&parent);
  missing.Reserve(&child);
  missing.Freeze();
  missing.BeginNode(&parent, 1, "Parent");
  missing.EndNode();
  ExpectThrows<std::logic_error>([&] { missing.Finish(); },
                                 "finish with missing node");
  missing.BeginNode(&child, 2, "Child");
  missing.EndNode();
  missing.Finish();
}

} // namespace

int main() {
  try {
    TestPrewalkAndEmission();
    TestPhaseAndAttributeErrors();
    TestEmissionOrderAndMissingNode();
    std::cout << "binary_context_test: all checks passed\n";
  } catch (const std::exception& error) {
    std::cerr << "binary_context_test: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
