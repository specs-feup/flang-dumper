#ifndef FLANG_DUMPER_PROTOCOL_AST_WRITER_HPP
#define FLANG_DUMPER_PROTOCOL_AST_WRITER_HPP

#include <cstdint>
#include <memory>
#include <ostream>
#include <string>
#include <vector>

#include "protocol/ast_stream.pb.h"

namespace flang_dumper::protocol {

struct AttributeSpec {
  std::string key;
  AttributeValue value;
};

class AstWriter final {
public:
  // Takes ownership of output and writes the stream header immediately.
  explicit AstWriter(std::unique_ptr<std::ostream> output);

  AstWriter(const AstWriter&) = delete;
  AstWriter& operator=(const AstWriter&) = delete;
  AstWriter(AstWriter&&) = delete;
  AstWriter& operator=(AstWriter&&) = delete;

  std::uint64_t WriteNode(std::uint32_t kind_id, std::string kind_name,
                          const std::vector<AttributeSpec>& attributes);
  void WriteComment(std::string text, std::uint64_t stmt_node_id,
                    bool trailing);
  void WriteEnumCatalog(std::string type_name,
                        const std::vector<EnumEntry>& entries);

private:
  void Emit(const StreamRecord& record);
  void ValidateValue(const AttributeValue& value) const;
  void ValidateList(const ValueList& values) const;
  void ValidateReference(std::uint64_t reference) const;
  void ValidateExistingNode(std::uint64_t node_id) const;
  void EnsureWritable() const;

  std::unique_ptr<std::ostream> output_;
  std::uint64_t next_node_id_ = 1;
  bool ids_exhausted_ = false;
  bool failed_ = false;
};

} // namespace flang_dumper::protocol

#endif // FLANG_DUMPER_PROTOCOL_AST_WRITER_HPP
