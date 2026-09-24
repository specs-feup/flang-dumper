#include "protocol/ast_writer.hpp"

#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "protocol/framing.hpp"

namespace {

using flang_dumper::protocol::AstWriter;
using flang_dumper::protocol::AttributeSpec;
using flang_dumper::protocol::AttributeValue;
using flang_dumper::protocol::EnumEntry;
using flang_dumper::protocol::ProtocolError;
using flang_dumper::protocol::ReadHeader;
using flang_dumper::protocol::ReadRecord;
using flang_dumper::protocol::StreamRecord;
using flang_dumper::protocol::Value;

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

AttributeSpec StringAttribute(std::string key, const std::string& value) {
  AttributeSpec attribute;
  attribute.key = std::move(key);
  attribute.value.set_string_value(value);
  return attribute;
}

AttributeSpec ReferenceAttribute(std::string key, std::uint64_t reference) {
  AttributeSpec attribute;
  attribute.key = std::move(key);
  attribute.value.set_node_reference(reference);
  return attribute;
}

AttributeSpec EmptyListAttribute(std::string key) {
  AttributeSpec attribute;
  attribute.key = std::move(key);
  attribute.value.mutable_list_value();
  return attribute;
}

void TestWriteAndRoundTrip() {
  auto owned_output = std::make_unique<std::ostringstream>(std::ios::binary);
  auto* captured_output = owned_output.get();
  std::string bytes;
  {
    AstWriter writer(std::move(owned_output));
    Check(writer.WriteNode(42, "RootNode", {}) == 1,
          "first assigned node ID must be 1");

    AttributeSpec nested;
    nested.key = "nested";
    auto* outer_list = nested.value.mutable_list_value();
    outer_list->add_items()->set_string_value("first");
    auto* nested_list = outer_list->add_items()->mutable_list_value();
    nested_list->add_items()->set_node_reference(1);
    outer_list->add_items()->set_bool_value(false);

    AttributeSpec empty_list = EmptyListAttribute("empty_list");
    AttributeSpec empty_bytes;
    empty_bytes.key = "bytes";
    empty_bytes.value.set_bytes_value(std::string("\0\xff", 2));
    AttributeSpec double_zero;
    double_zero.key = "double";
    double_zero.value.set_double_value(0.0);
    const std::vector<AttributeSpec> attributes{
        StringAttribute("exact.Key", "value"),
        ReferenceAttribute("parent", 1), nested, empty_list, empty_bytes,
        double_zero};
    Check(writer.WriteNode(7, "ChildNode", attributes) == 2,
          "second assigned node ID must be 2");

    writer.WriteComment("trailing comment", 1, true);
    std::vector<EnumEntry> entries(2);
    entries[0].set_name("First");
    entries[0].set_number(0);
    entries[1].set_name("Second");
    entries[1].set_number(-3);
    writer.WriteEnumCatalog("ExampleEnum", entries);
    bytes = captured_output->str();
  }

  std::istringstream input(bytes, std::ios::binary);
  ReadHeader(input);
  StreamRecord record;
  Check(ReadRecord(input, record), "first record should be present");
  Check(record.has_node() && record.node().node_id() == 1 &&
            record.node().kind_id() == 42 && record.node().kind_name() == "RootNode",
        "first node fields did not round-trip");

  Check(ReadRecord(input, record), "second record should be present");
  Check(record.has_node() && record.node().node_id() == 2 &&
            record.node().kind_id() == 7 && record.node().kind_name() == "ChildNode",
        "second node fields did not round-trip");
  const auto& attributes = record.node().attributes();
  Check(attributes.size() == 6, "attributes must retain their count and order");
  Check(attributes[0].key() == "exact.Key" &&
            attributes[0].value().string_value() == "value",
        "attribute keys and values must be preserved exactly");
  Check(attributes[1].key() == "parent" &&
            attributes[1].value().node_reference() == 1,
        "node reference did not round-trip");
  Check(attributes[2].key() == "nested" &&
            attributes[2].value().list_value().items_size() == 3,
        "nested list did not round-trip");
  Check(attributes[2].value().list_value().items(1).list_value().items(0)
                .node_reference() == 1,
        "nested list node reference did not round-trip");
  Check(attributes[3].key() == "empty_list" &&
            attributes[3].value().has_list_value() &&
            attributes[3].value().list_value().items().empty(),
        "present empty list did not round-trip");
  Check(attributes[4].value().bytes_value() == std::string("\0\xff", 2),
        "bytes value did not round-trip");
  Check(attributes[5].value().double_value() == 0.0,
        "double value did not round-trip");

  Check(ReadRecord(input, record) && record.has_comment(),
        "comment record should be present");
  Check(record.comment().text() == "trailing comment" &&
            record.comment().stmt_node_id() == 1 && record.comment().trailing(),
        "comment fields did not round-trip");

  Check(ReadRecord(input, record) && record.has_enum_catalog(),
        "enum catalog record should be present");
  Check(record.enum_catalog().enum_type_name() == "ExampleEnum" &&
            record.enum_catalog().entries_size() == 2 &&
            record.enum_catalog().entries(1).name() == "Second" &&
            record.enum_catalog().entries(1).number() == -3,
        "enum catalog entries did not round-trip");
  Check(!ReadRecord(input, record), "EOF between records should be clean");
}

void TestRejectsInvalidInputWithoutConsumingIDs() {
  auto owned_output = std::make_unique<std::ostringstream>(std::ios::binary);
  auto* captured_output = owned_output.get();
  AstWriter writer(std::move(owned_output));

  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteNode(0, "Kind", {}); }, "zero kind ID");
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteNode(1, "", {}); }, "empty kind name");
  ExpectThrows<std::invalid_argument>(
      [&] {
        writer.WriteNode(1, "Kind", {StringAttribute("same", "a"),
                                      StringAttribute("same", "b")});
      },
      "duplicate attribute keys");
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteNode(1, "Kind", {ReferenceAttribute("zero", 0)}); },
      "zero node reference");

  AttributeSpec missing_value;
  missing_value.key = "missing";
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteNode(1, "Kind", {missing_value}); },
      "missing AttributeValue case");

  AttributeSpec missing_list_item;
  missing_list_item.key = "missing_list_item";
  missing_list_item.value.mutable_list_value()->add_items();
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteNode(1, "Kind", {missing_list_item}); },
      "missing Value case in list");

  Check(writer.WriteNode(1, "Kind", {}) == 1,
        "rejected nodes must not consume node IDs");
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteComment("future", 2, false); },
      "comment reference to future node");
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteComment("zero", 0, false); },
      "zero comment statement ID");
  writer.WriteComment("valid", 1, false);

  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteEnumCatalog("", {}); }, "empty enum type name");
  std::vector<EnumEntry> empty_name(1);
  empty_name[0].set_number(1);
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteEnumCatalog("Enum", empty_name); },
      "empty enum entry name");
  std::vector<EnumEntry> duplicate_names(2);
  duplicate_names[0].set_name("Same");
  duplicate_names[1].set_name("Same");
  ExpectThrows<std::invalid_argument>(
      [&] { writer.WriteEnumCatalog("Enum", duplicate_names); },
      "duplicate enum entry names");

  std::istringstream input(captured_output->str(), std::ios::binary);
  ReadHeader(input);
  StreamRecord record;
  Check(ReadRecord(input, record) && record.has_node() &&
            record.node().node_id() == 1,
        "invalid input must not emit records or consume IDs");
  Check(ReadRecord(input, record) && record.has_comment(),
        "valid comment should be emitted after the node");
  Check(!ReadRecord(input, record), "invalid catalogs must not be emitted");
}

void TestForwardReferencesPassThrough() {
  auto owned_output = std::make_unique<std::ostringstream>(std::ios::binary);
  auto* captured_output = owned_output.get();
  AstWriter writer(std::move(owned_output));

  AttributeSpec child_reference = ReferenceAttribute("child", 2);
  AttributeSpec descendants;
  descendants.key = "descendants";
  descendants.value.mutable_list_value()->add_items()->set_node_reference(3);
  Check(writer.WriteNode(1, "Parent", {child_reference, descendants}) == 1,
        "parent node should be written before its referenced nodes");
  Check(writer.WriteNode(2, "Child", {}) == 2,
        "child node should receive its referenced ID");
  Check(writer.WriteNode(3, "Grandchild", {}) == 3,
        "grandchild node should receive its referenced ID");

  std::istringstream input(captured_output->str(), std::ios::binary);
  ReadHeader(input);
  StreamRecord record;
  Check(ReadRecord(input, record) && record.has_node() &&
            record.node().node_id() == 1,
        "parent record should be present");
  const auto& attributes = record.node().attributes();
  Check(attributes.size() == 2 &&
            attributes[0].value().node_reference() == 2,
        "direct forward reference should pass through unchanged");
  Check(attributes[1].value().list_value().items_size() == 1 &&
            attributes[1].value().list_value().items(0).node_reference() == 3,
        "list forward reference should pass through unchanged");
  Check(ReadRecord(input, record) && record.has_node() &&
            record.node().node_id() == 2,
        "child record should follow its parent");
  Check(ReadRecord(input, record) && record.has_node() &&
            record.node().node_id() == 3,
        "grandchild record should follow its parent");
  Check(!ReadRecord(input, record), "EOF between records should be clean");
}

void TestRejectsNullOutput() {
  ExpectThrows<std::invalid_argument>(
      [] { AstWriter writer(std::unique_ptr<std::ostream>{}); },
      "null owned stream");
}

} // namespace

int main() {
  try {
    TestWriteAndRoundTrip();
    TestRejectsInvalidInputWithoutConsumingIDs();
    TestForwardReferencesPassThrough();
    TestRejectsNullOutput();
  } catch (const std::exception& error) {
    std::cerr << "AstWriter tests failed: " << error.what() << '\n';
    return 1;
  }

  std::cout << "AstWriter tests passed\n";
  return 0;
}
