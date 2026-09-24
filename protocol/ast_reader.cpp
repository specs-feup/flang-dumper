#include "protocol/ast_reader.hpp"

#include <istream>
#include <string>
#include <unordered_set>
#include <vector>

#include "protocol/framing.hpp"

namespace flang_dumper::protocol {

AstReader::AstReader(std::istream& input) : input_(input) { ReadHeader(input_); }

bool AstReader::ReadNext(StreamRecord& output) {
  if (clean_eof_) {
    return false;
  }

  if (!ReadRecord(input_, output)) {
    clean_eof_ = true;
    return false;
  }

  ValidateRecord(output);
  return true;
}

void AstReader::Finish() const {
  if (!clean_eof_) {
    throw ProtocolError("AstReader::Finish called before clean EOF");
  }
  if (node_ids_.empty()) {
    throw ProtocolError("AST stream must contain at least one node");
  }
  if (!first_record_was_node_) {
    throw ProtocolError("first AST stream record must be a node");
  }
  for (const auto reference : referenced_ids_) {
    if (node_ids_.find(reference) == node_ids_.end()) {
      throw ProtocolError("AST stream contains a reference to a missing node");
    }
  }
}

void AstReader::ValidateRecord(const StreamRecord& record) {
  std::unordered_set<std::uint64_t> references;

  switch (record.record_case()) {
  case StreamRecord::kNode: {
    const NodeRecord& node = record.node();
    if (node.node_id() == 0) {
      throw ProtocolError("node ID must be nonzero");
    }
    if (node_ids_.find(node.node_id()) != node_ids_.end()) {
      throw ProtocolError("duplicate node ID");
    }
    if (node.kind_id() == 0) {
      throw ProtocolError("node kind ID must be nonzero");
    }
    if (node.kind_name().empty()) {
      throw ProtocolError("node kind name must be nonempty");
    }

    for (const auto& attribute : node.attributes()) {
      if (attribute.key().empty()) {
        throw ProtocolError("node attribute key must be nonempty");
      }
      ValidateAttributeValue(attribute.value(), references);
    }

    node_ids_.insert(node.node_id());
    break;
  }
  case StreamRecord::kComment: {
    const auto stmt_node_id = record.comment().stmt_node_id();
    if (stmt_node_id == 0) {
      throw ProtocolError("comment statement node ID must be nonzero");
    }
    references.insert(stmt_node_id);
    break;
  }
  case StreamRecord::kEnumCatalog: {
    const EnumCatalog& catalog = record.enum_catalog();
    if (catalog.enum_type_name().empty()) {
      throw ProtocolError("enum catalog type name must be nonempty");
    }
    std::unordered_set<std::string> names;
    for (const auto& entry : catalog.entries()) {
      if (entry.name().empty()) {
        throw ProtocolError("enum entry name must be nonempty");
      }
      if (!names.insert(entry.name()).second) {
        throw ProtocolError("duplicate enum entry name");
      }
    }
    break;
  }
  case StreamRecord::RECORD_NOT_SET:
    throw ProtocolError("stream record oneof must be set");
  }

  if (!saw_record_) {
    first_record_was_node_ = record.has_node();
    saw_record_ = true;
  }
  referenced_ids_.insert(references.begin(), references.end());
}

void AstReader::ValidateAttributeValue(
    const AttributeValue& value,
    std::unordered_set<std::uint64_t>& references) const {
  switch (value.value_case()) {
  case AttributeValue::VALUE_NOT_SET:
    throw ProtocolError("attribute value oneof must be set");
  case AttributeValue::kNodeReference:
    if (value.node_reference() == 0) {
      throw ProtocolError("node reference must be nonzero");
    }
    references.insert(value.node_reference());
    return;
  case AttributeValue::kListValue:
    ValidateList(value.list_value(), references);
    return;
  case AttributeValue::kStringValue:
  case AttributeValue::kIntegerValue:
  case AttributeValue::kBoolValue:
  case AttributeValue::kNullValue:
  case AttributeValue::kDoubleValue:
  case AttributeValue::kBytesValue:
    return;
  }
  throw ProtocolError("attribute value has an unknown case");
}

void AstReader::ValidateList(
    const ValueList& values,
    std::unordered_set<std::uint64_t>& references) const {
  // An explicit worklist avoids using the C++ call stack for nested lists.
  std::vector<const Value*> pending;
  pending.reserve(static_cast<std::size_t>(values.items_size()));
  for (const auto& item : values.items()) {
    pending.push_back(&item);
  }

  while (!pending.empty()) {
    const Value& item = *pending.back();
    pending.pop_back();
    switch (item.value_case()) {
    case Value::VALUE_NOT_SET:
      throw ProtocolError("list item value oneof must be set");
    case Value::kNodeReference:
      if (item.node_reference() == 0) {
        throw ProtocolError("node reference must be nonzero");
      }
      references.insert(item.node_reference());
      break;
    case Value::kListValue:
      for (const auto& nested_item : item.list_value().items()) {
        pending.push_back(&nested_item);
      }
      break;
    case Value::kStringValue:
    case Value::kIntegerValue:
    case Value::kBoolValue:
    case Value::kNullValue:
    case Value::kDoubleValue:
    case Value::kBytesValue:
      break;
    }
  }
}

} // namespace flang_dumper::protocol
