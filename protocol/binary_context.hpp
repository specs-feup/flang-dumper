#ifndef FLANG_DUMPER_PROTOCOL_BINARY_CONTEXT_HPP
#define FLANG_DUMPER_PROTOCOL_BINARY_CONTEXT_HPP

#include <cstdint>
#include <memory>
#include <ostream>
#include <string>
#include <vector>

#include "protocol/ast_writer.hpp"
#include "protocol/graph_ids.hpp"

namespace flang_dumper::protocol {

// Owns the node identity map and writer for a two-pass graph emission.
class BinaryContext final {
public:
  explicit BinaryContext(std::unique_ptr<std::ostream> output);

  BinaryContext(const BinaryContext&) = delete;
  BinaryContext& operator=(const BinaryContext&) = delete;
  BinaryContext(BinaryContext&&) = delete;
  BinaryContext& operator=(BinaryContext&&) = delete;

  // Prewalk phase. Repeated reservations keep their original identity.
  void Reserve(const void* identity);
  void Freeze();

  // Emission phase. References may point to any prewalked node, including a
  // node that will be emitted later.
  void BeginNode(const void* identity, std::uint32_t kind_id,
                 std::string kind_name);
  void AddString(std::string key, std::string value);
  void AddInteger(std::string key, std::int64_t value);
  void AddBool(std::string key, bool value);
  void AddDouble(std::string key, double value);
  void AddBytes(std::string key, std::string value);
  void AddReference(std::string key, const void* identity);
  void AddReferenceList(std::string key,
                        const std::vector<const void*>& identities);
  void AddNull(std::string key);
  void EndNode();
  void WriteComment(std::string text, const void* stmt_identity,
                    bool trailing);
  void WriteEnumCatalog(std::string type_name,
                        const std::vector<EnumEntry>& entries);

  // Completes emission after every reserved node has been written.
  void Finish();

private:
  AttributeValue& NewAttributeValue(std::string key);
  void EnsureHealthy() const;
  void EnsureOpenNode() const;
  void EnsureRecordBoundary() const;

  GraphIds graph_ids_;
  AstWriter writer_;
  const void* open_identity_ = nullptr;
  std::uint32_t open_kind_id_ = 0;
  std::string open_kind_name_;
  std::vector<AttributeSpec> open_attributes_;
  bool frozen_ = false;
  bool finished_ = false;
  bool failed_ = false;
};

} // namespace flang_dumper::protocol

#endif // FLANG_DUMPER_PROTOCOL_BINARY_CONTEXT_HPP
