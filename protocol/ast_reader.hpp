#ifndef FLANG_DUMPER_PROTOCOL_AST_READER_HPP
#define FLANG_DUMPER_PROTOCOL_AST_READER_HPP

#include <cstdint>
#include <iosfwd>
#include <unordered_set>

#include "protocol/ast_stream.pb.h"

namespace flang_dumper::protocol {

class AstReader final {
public:
  // Borrows input and reads the protocol header during construction.
  explicit AstReader(std::istream& input);

  AstReader(const AstReader&) = delete;
  AstReader& operator=(const AstReader&) = delete;
  AstReader(AstReader&&) = delete;
  AstReader& operator=(AstReader&&) = delete;

  // Reads and validates the next record into output. Returns false only after
  // clean EOF between records.
  bool ReadNext(StreamRecord& output);

  // Verifies end-of-stream invariants after ReadNext has observed clean EOF.
  void Finish() const;

private:
  void ValidateRecord(const StreamRecord& record);
  void ValidateAttributeValue(const AttributeValue& value,
                             std::unordered_set<std::uint64_t>& references) const;
  void ValidateList(const ValueList& values,
                    std::unordered_set<std::uint64_t>& references) const;

  std::istream& input_;
  std::unordered_set<std::uint64_t> node_ids_;
  std::unordered_set<std::uint64_t> referenced_ids_;
  bool saw_record_ = false;
  bool first_record_was_node_ = false;
  bool clean_eof_ = false;
};

} // namespace flang_dumper::protocol

#endif // FLANG_DUMPER_PROTOCOL_AST_READER_HPP
