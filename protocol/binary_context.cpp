#include "protocol/binary_context.hpp"

#include <stdexcept>
#include <utility>

namespace flang_dumper::protocol {

BinaryContext::BinaryContext(std::unique_ptr<std::ostream> output)
    : writer_(std::move(output)) {}

void BinaryContext::Reserve(const void* identity) {
  EnsureHealthy();
  if (frozen_) {
    throw std::logic_error("cannot reserve a node after BinaryContext is frozen");
  }
  graph_ids_.Reserve(identity);
}

void BinaryContext::Freeze() {
  EnsureHealthy();
  if (frozen_) {
    throw std::logic_error("BinaryContext is already frozen");
  }
  graph_ids_.Freeze();
  frozen_ = true;
}

void BinaryContext::BeginNode(const void* identity, std::uint32_t kind_id,
                              std::string kind_name) {
  EnsureHealthy();
  if (!frozen_) {
    throw std::logic_error("cannot begin a node before BinaryContext is frozen");
  }
  if (open_identity_ != nullptr) {
    throw std::logic_error("cannot begin a node while another node is open");
  }
  graph_ids_.Lookup(identity);
  if (kind_id == 0) {
    throw std::invalid_argument("node kind_id must be nonzero");
  }
  if (kind_name.empty()) {
    throw std::invalid_argument("node kind_name must be nonempty");
  }

  open_identity_ = identity;
  open_kind_id_ = kind_id;
  open_kind_name_ = std::move(kind_name);
  open_attributes_.clear();
}

void BinaryContext::AddString(std::string key, std::string value) {
  NewAttributeValue(std::move(key)).set_string_value(std::move(value));
}

void BinaryContext::AddInteger(std::string key, std::int64_t value) {
  NewAttributeValue(std::move(key)).set_integer_value(value);
}

void BinaryContext::AddBool(std::string key, bool value) {
  NewAttributeValue(std::move(key)).set_bool_value(value);
}

void BinaryContext::AddDouble(std::string key, double value) {
  NewAttributeValue(std::move(key)).set_double_value(value);
}

void BinaryContext::AddBytes(std::string key, std::string value) {
  NewAttributeValue(std::move(key)).set_bytes_value(std::move(value));
}

void BinaryContext::AddReference(std::string key, const void* identity) {
  EnsureOpenNode();
  if (key.empty()) {
    throw std::invalid_argument("node attribute key must be nonempty");
  }
  const std::uint64_t id = graph_ids_.Lookup(identity);
  NewAttributeValue(std::move(key)).set_node_reference(id);
}

void BinaryContext::AddReferenceList(
    std::string key, const std::vector<const void*>& identities) {
  EnsureOpenNode();
  if (key.empty()) {
    throw std::invalid_argument("node attribute key must be nonempty");
  }

  std::vector<std::uint64_t> ids;
  ids.reserve(identities.size());
  for (const void* identity : identities) {
    ids.push_back(graph_ids_.Lookup(identity));
  }

  AttributeValue& value = NewAttributeValue(std::move(key));
  auto* list = value.mutable_list_value();
  for (const std::uint64_t id : ids) {
    list->add_items()->set_node_reference(id);
  }
}

void BinaryContext::AddNull(std::string key) {
  NewAttributeValue(std::move(key)).mutable_null_value();
}

void BinaryContext::EndNode() {
  EnsureOpenNode();
  const void* identity = open_identity_;
  const std::uint64_t reserved_id = graph_ids_.Lookup(identity);

  // Check and record the prewalk order before writing. If output then fails,
  // poison the context so it cannot report a successful Finish.
  graph_ids_.VerifyEmission(identity, reserved_id);
  try {
    const std::uint64_t written_id = writer_.WriteNode(
        open_kind_id_, std::move(open_kind_name_), open_attributes_);
    if (written_id != reserved_id) {
      failed_ = true;
      throw std::logic_error("AstWriter node ID does not match its reserved ID");
    }
  } catch (...) {
    failed_ = true;
    throw;
  }

  open_identity_ = nullptr;
  open_kind_id_ = 0;
  open_kind_name_.clear();
  open_attributes_.clear();
}

void BinaryContext::WriteComment(std::string text, const void* stmt_identity,
                                 bool trailing) {
  EnsureRecordBoundary();
  const std::uint64_t stmt_node_id = graph_ids_.Lookup(stmt_identity);
  try {
    writer_.WriteComment(std::move(text), stmt_node_id, trailing);
  } catch (const std::invalid_argument&) {
    throw;
  } catch (...) {
    failed_ = true;
    throw;
  }
}

void BinaryContext::WriteEnumCatalog(
    std::string type_name, const std::vector<EnumEntry>& entries) {
  EnsureRecordBoundary();
  try {
    writer_.WriteEnumCatalog(std::move(type_name), entries);
  } catch (const std::invalid_argument&) {
    throw;
  } catch (...) {
    failed_ = true;
    throw;
  }
}

void BinaryContext::Finish() {
  EnsureHealthy();
  if (!frozen_) {
    throw std::logic_error("cannot finish BinaryContext before it is frozen");
  }
  if (open_identity_ != nullptr) {
    throw std::logic_error("cannot finish BinaryContext while a node is open");
  }
  if (finished_) {
    throw std::logic_error("BinaryContext is already finished");
  }
  graph_ids_.Finish();
  finished_ = true;
}

AttributeValue& BinaryContext::NewAttributeValue(std::string key) {
  EnsureOpenNode();
  if (key.empty()) {
    throw std::invalid_argument("node attribute key must be nonempty");
  }
  open_attributes_.emplace_back();
  open_attributes_.back().key = std::move(key);
  return open_attributes_.back().value;
}

void BinaryContext::EnsureHealthy() const {
  if (failed_) {
    throw std::logic_error("BinaryContext cannot continue after an output failure");
  }
  if (finished_) {
    throw std::logic_error("BinaryContext is already finished");
  }
}

void BinaryContext::EnsureOpenNode() const {
  EnsureHealthy();
  if (!frozen_) {
    throw std::logic_error("cannot add a node attribute before BinaryContext is frozen");
  }
  if (open_identity_ == nullptr) {
    throw std::logic_error("cannot add an attribute without an open node");
  }
}

void BinaryContext::EnsureRecordBoundary() const {
  EnsureHealthy();
  if (!frozen_) {
    throw std::logic_error("cannot write a record before BinaryContext is frozen");
  }
  if (open_identity_ != nullptr) {
    throw std::logic_error("cannot write a record while a node is open");
  }
}

} // namespace flang_dumper::protocol
