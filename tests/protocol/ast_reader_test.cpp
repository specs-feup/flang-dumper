#include "protocol/ast_reader.hpp"

#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include "protocol/framing.hpp"

namespace {

using flang_dumper::protocol::AstReader;
using flang_dumper::protocol::ProtocolError;
using flang_dumper::protocol::StreamRecord;
using flang_dumper::protocol::WriteHeader;
using flang_dumper::protocol::WriteRecord;

void Check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Function>
void ExpectProtocolError(Function&& function, const std::string& test_name) {
  try {
    function();
  } catch (const ProtocolError&) {
    return;
  }
  throw std::runtime_error(test_name + ": expected ProtocolError");
}

StreamRecord Node(std::uint64_t id, std::uint32_t kind_id = 1,
                  const std::string& kind_name = "Node") {
  StreamRecord record;
  auto* node = record.mutable_node();
  node->set_node_id(id);
  node->set_kind_id(kind_id);
  node->set_kind_name(kind_name);
  return record;
}

std::string Encode(const std::vector<StreamRecord>& records) {
  std::ostringstream output(std::ios::binary);
  WriteHeader(output);
  for (const auto& record : records) {
    WriteRecord(output, record);
  }
  return output.str();
}

void ReadToEnd(AstReader& reader) {
  StreamRecord record;
  while (reader.ReadNext(record)) {
  }
}

void ExpectBadStream(const std::string& bytes, const std::string& name) {
  std::istringstream input(bytes, std::ios::binary);
  AstReader reader(input);
  ExpectProtocolError([&] { ReadToEnd(reader); }, name);
}

void TestValidForwardReferencesAndEmptyList() {
  StreamRecord root = Node(1);
  auto* child_ref = root.mutable_node()->add_attributes();
  child_ref->set_key("child");
  child_ref->mutable_value()->set_node_reference(2);
  auto* list_ref = root.mutable_node()->add_attributes();
  list_ref->set_key("nested");
  list_ref->mutable_value()->mutable_list_value()->add_items()->set_node_reference(3);
  auto* empty_list = root.mutable_node()->add_attributes();
  empty_list->set_key("empty");
  empty_list->mutable_value()->mutable_list_value();

  const std::string bytes = Encode({root, Node(2), Node(3)});
  std::istringstream input(bytes, std::ios::binary);
  AstReader reader(input);
  StreamRecord output;
  Check(reader.ReadNext(output) && output.has_node() &&
            output.node().attributes_size() == 3,
        "root node should be returned to the caller");
  Check(output.node().attributes(2).value().has_list_value() &&
            output.node().attributes(2).value().list_value().items().empty(),
        "present empty list should remain distinct from absent value");
  Check(reader.ReadNext(output) && output.node().node_id() == 2,
        "first forward reference target should be returned");
  Check(reader.ReadNext(output) && output.node().node_id() == 3,
        "nested forward reference target should be returned");
  Check(!reader.ReadNext(output), "reader should report clean EOF");
  Check(!reader.ReadNext(output), "repeated read after clean EOF should be false");
  reader.Finish();
}

void TestFinishRequiresCleanEof() {
  std::istringstream input(Encode({Node(1)}), std::ios::binary);
  AstReader reader(input);
  ExpectProtocolError([&] { reader.Finish(); }, "Finish before EOF");
}

void TestBadHeaders() {
  std::string wrong_magic = Encode({Node(1)});
  wrong_magic[0] = 'X';
  std::istringstream bad_magic(wrong_magic, std::ios::binary);
  ExpectProtocolError([&] { AstReader reader(bad_magic); }, "wrong header magic");

  std::string wrong_version = Encode({Node(1)});
  wrong_version[8] = 2;
  std::istringstream bad_version(wrong_version, std::ios::binary);
  ExpectProtocolError([&] { AstReader reader(bad_version); }, "wrong header version");

  std::istringstream truncated(Encode({Node(1)}).substr(0, 11), std::ios::binary);
  ExpectProtocolError([&] { AstReader reader(truncated); }, "truncated header");
}

void TestDuplicateNodeIDs() {
  ExpectBadStream(Encode({Node(1), Node(1)}), "duplicate node IDs");
}

void TestMissingReferences() {
  StreamRecord root = Node(1);
  auto* attribute = root.mutable_node()->add_attributes();
  attribute->set_key("future");
  attribute->mutable_value()->set_node_reference(99);

  std::istringstream input(Encode({root}), std::ios::binary);
  AstReader reader(input);
  ReadToEnd(reader);
  ExpectProtocolError([&] { reader.Finish(); }, "unresolved node reference");
}

void TestCommentReferences() {
  StreamRecord root = Node(1);
  StreamRecord comment;
  comment.mutable_comment()->set_text("reference to a later node");
  comment.mutable_comment()->set_stmt_node_id(2);
  StreamRecord child = Node(2);
  std::istringstream input(Encode({root, comment, child}), std::ios::binary);
  AstReader reader(input);
  ReadToEnd(reader);
  reader.Finish();

  comment.mutable_comment()->set_stmt_node_id(0);
  ExpectBadStream(Encode({root, comment}), "zero comment statement ID");
  comment.mutable_comment()->set_stmt_node_id(9);
  std::istringstream unresolved_input(Encode({root, comment}), std::ios::binary);
  AstReader unresolved_reader(unresolved_input);
  ReadToEnd(unresolved_reader);
  ExpectProtocolError([&] { unresolved_reader.Finish(); },
                      "unresolved comment statement ID");
}

void TestNoRootNode() {
  StreamRecord catalog;
  catalog.mutable_enum_catalog()->set_enum_type_name("Example");
  std::istringstream input(Encode({catalog, Node(1)}), std::ios::binary);
  AstReader reader(input);
  ReadToEnd(reader);
  ExpectProtocolError([&] { reader.Finish(); }, "first record is not root node");

  std::istringstream empty_input(Encode({}), std::ios::binary);
  AstReader empty_reader(empty_input);
  ReadToEnd(empty_reader);
  ExpectProtocolError([&] { empty_reader.Finish(); }, "stream has no root node");
}

void TestMalformedValuesAndKeys() {
  StreamRecord missing_attribute_value = Node(1);
  auto* missing_value_attr = missing_attribute_value.mutable_node()->add_attributes();
  missing_value_attr->set_key("missing");
  ExpectBadStream(Encode({missing_attribute_value}), "missing AttributeValue oneof");

  StreamRecord missing_nested_value = Node(1);
  auto* nested_attr = missing_nested_value.mutable_node()->add_attributes();
  nested_attr->set_key("nested");
  nested_attr->mutable_value()->mutable_list_value()->add_items();
  ExpectBadStream(Encode({missing_nested_value}), "missing nested Value oneof");

  StreamRecord zero_reference = Node(1);
  auto* zero_ref_attr = zero_reference.mutable_node()->add_attributes();
  zero_ref_attr->set_key("zero");
  zero_ref_attr->mutable_value()->set_node_reference(0);
  ExpectBadStream(Encode({zero_reference}), "zero direct node reference");

  StreamRecord duplicate_keys = Node(1);
  for (int i = 0; i < 2; ++i) {
    auto* attribute = duplicate_keys.mutable_node()->add_attributes();
    attribute->set_key("same");
    attribute->mutable_value()->set_bool_value(false);
  }
  ExpectBadStream(Encode({duplicate_keys}), "duplicate attribute keys");

  StreamRecord empty_key = Node(1);
  auto* empty_attr = empty_key.mutable_node()->add_attributes();
  empty_attr->mutable_value()->set_string_value("value");
  ExpectBadStream(Encode({empty_key}), "empty attribute key");
}

void TestInvalidNodeAndEnumRecords() {
  ExpectBadStream(Encode({Node(0)}), "zero node ID");
  ExpectBadStream(Encode({Node(1, 0)}), "zero node kind ID");
  ExpectBadStream(Encode({Node(1, 1, "")}), "empty node kind name");

  StreamRecord empty_type;
  empty_type.mutable_enum_catalog();
  ExpectBadStream(Encode({Node(1), empty_type}), "empty enum type name");

  StreamRecord empty_entry;
  empty_entry.mutable_enum_catalog()->set_enum_type_name("Example");
  empty_entry.mutable_enum_catalog()->add_entries()->set_number(1);
  ExpectBadStream(Encode({Node(1), empty_entry}), "empty enum entry name");

  StreamRecord duplicate_entries;
  auto* catalog = duplicate_entries.mutable_enum_catalog();
  catalog->set_enum_type_name("Example");
  catalog->add_entries()->set_name("same");
  catalog->add_entries()->set_name("same");
  ExpectBadStream(Encode({Node(1), duplicate_entries}), "duplicate enum entry names");
}

void TestRecordOneofMustBeSet() {
  std::ostringstream output(std::ios::binary);
  WriteHeader(output);
  // Protobuf serializes an empty message to zero bytes, which framing rejects.
  // Encode the legal unknown-field payload directly as a nonempty record.
  output.put(static_cast<char>(2));
  output.put(static_cast<char>(0x78)); // Unknown varint field 15, value follows.
  output.put(static_cast<char>(0));
  std::istringstream input(output.str(), std::ios::binary);
  AstReader reader(input);
  StreamRecord record;
  ExpectProtocolError([&] { reader.ReadNext(record); }, "unset record oneof");
}

} // namespace

int main() {
  try {
    TestValidForwardReferencesAndEmptyList();
    TestFinishRequiresCleanEof();
    TestBadHeaders();
    TestDuplicateNodeIDs();
    TestMissingReferences();
    TestCommentReferences();
    TestNoRootNode();
    TestMalformedValuesAndKeys();
    TestInvalidNodeAndEnumRecords();
    TestRecordOneofMustBeSet();
  } catch (const std::exception& error) {
    std::cerr << "AstReader tests failed: " << error.what() << '\n';
    return 1;
  }

  std::cout << "AstReader tests passed\n";
  return 0;
}
