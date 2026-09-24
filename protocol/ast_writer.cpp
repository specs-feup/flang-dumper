#include "protocol/ast_writer.hpp"

#include <limits>
#include <stdexcept>
#include <unordered_set>
#include <utility>

#include "protocol/framing.hpp"

namespace flang_dumper::protocol {

AstWriter::AstWriter(std::unique_ptr<std::ostream> output)
    : output_(std::move(output)) {
  if (!output_) {
    throw std::invalid_argument("AstWriter requires an owned output stream");
  }
  if (!*output_) {
    throw ProtocolError("AstWriter output stream is not writable");
  }
  WriteHeader(*output_);
}

std::uint64_t AstWriter::WriteNode(
    std::uint32_t kind_id, std::string kind_name,
    const std::vector<AttributeSpec>& attributes) {
  EnsureWritable();
  if (ids_exhausted_) {
    throw std::overflow_error("AstWriter exhausted uint64 node IDs");
  }
  if (kind_id == 0) {
    throw std::invalid_argument("node kind_id must be nonzero");
  }
  if (kind_name.empty()) {
    throw std::invalid_argument("node kind_name must be nonempty");
  }

  const std::uint64_t node_id = next_node_id_;
  for (const auto& attribute : attributes) {
    if (attribute.key.empty()) {
      throw std::invalid_argument("node attribute key must be nonempty");
    }
    ValidateValue(attribute.value);
  }

  StreamRecord record;
  auto* node = record.mutable_node();
  node->set_node_id(node_id);
  node->set_kind_id(kind_id);
  node->set_kind_name(std::move(kind_name));
  for (const auto& attribute : attributes) {
    auto* output_attribute = node->add_attributes();
    output_attribute->set_key(attribute.key);
    *output_attribute->mutable_value() = attribute.value;
  }

  Emit(record);
  if (node_id == std::numeric_limits<std::uint64_t>::max()) {
    ids_exhausted_ = true;
  } else {
    next_node_id_ = node_id + 1;
  }
  return node_id;
}

void AstWriter::WriteComment(std::string text, std::uint64_t stmt_node_id,
                             bool trailing) {
  EnsureWritable();
  ValidateExistingNode(stmt_node_id);

  StreamRecord record;
  auto* comment = record.mutable_comment();
  comment->set_text(std::move(text));
  comment->set_stmt_node_id(stmt_node_id);
  comment->set_trailing(trailing);
  Emit(record);
}

void AstWriter::WriteEnumCatalog(std::string type_name,
                                 const std::vector<EnumEntry>& entries) {
  EnsureWritable();
  if (type_name.empty()) {
    throw std::invalid_argument("enum catalog type_name must be nonempty");
  }

  std::unordered_set<std::string> names;
  for (const auto& entry : entries) {
    if (entry.name().empty()) {
      throw std::invalid_argument("enum entry name must be nonempty");
    }
    if (!names.insert(entry.name()).second) {
      throw std::invalid_argument("duplicate enum entry name: " + entry.name());
    }
  }

  StreamRecord record;
  auto* catalog = record.mutable_enum_catalog();
  catalog->set_enum_type_name(std::move(type_name));
  for (const auto& entry : entries) {
    *catalog->add_entries() = entry;
  }
  Emit(record);
}

void AstWriter::Emit(const StreamRecord& record) {
  EnsureWritable();
  try {
    WriteRecord(*output_, record);
  } catch (...) {
    failed_ = true;
    throw;
  }
}

void AstWriter::ValidateValue(const AttributeValue& value) const {
  switch (value.value_case()) {
  case AttributeValue::VALUE_NOT_SET:
    throw std::invalid_argument("node attribute value oneof must be set");
  case AttributeValue::kNodeReference:
    ValidateReference(value.node_reference());
    return;
  case AttributeValue::kListValue:
    ValidateList(value.list_value());
    return;
  case AttributeValue::kStringValue:
  case AttributeValue::kIntegerValue:
  case AttributeValue::kBoolValue:
  case AttributeValue::kNullValue:
  case AttributeValue::kDoubleValue:
  case AttributeValue::kBytesValue:
    return;
  }
  throw std::invalid_argument("node attribute has an unknown value case");
}

void AstWriter::ValidateList(const ValueList& values) const {
  // Use an explicit worklist so deeply nested protobuf lists do not consume the
  // C++ call stack during validation.
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
      throw std::invalid_argument("list item value oneof must be set");
    case Value::kNodeReference:
      ValidateReference(item.node_reference());
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

void AstWriter::ValidateReference(std::uint64_t reference) const {
  if (reference == 0) {
    throw std::invalid_argument("node references must be nonzero");
  }
}

void AstWriter::ValidateExistingNode(std::uint64_t node_id) const {
  if (node_id == 0 || (!ids_exhausted_ && node_id >= next_node_id_)) {
    throw std::invalid_argument("comment statement ID must name an existing node");
  }
}

void AstWriter::EnsureWritable() const {
  if (failed_) {
    throw ProtocolError("AstWriter cannot continue after an output failure");
  }
}

} // namespace flang_dumper::protocol
