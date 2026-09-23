#ifndef FLANG_DUMPER_PROTOCOL_FRAMING_HPP
#define FLANG_DUMPER_PROTOCOL_FRAMING_HPP

#include <cstddef>
#include <cstdint>
#include <iosfwd>
#include <stdexcept>

#include <google/protobuf/message_lite.h>

namespace flang_dumper::protocol {

inline constexpr std::uint32_t kProtocolVersion = 1;
inline constexpr std::size_t kDefaultMaxRecordBytes = 64u * 1024u * 1024u;

class ProtocolError : public std::runtime_error {
public:
  using std::runtime_error::runtime_error;
};

// Writes the fixed protocol header. The version is encoded as little-endian
// uint32 after the eight-byte ASCII magic "FLASTPB1".
void WriteHeader(std::ostream& output);

// Reads and validates the fixed protocol header.
void ReadHeader(std::istream& input);

// Writes one non-empty protobuf wire message, prefixed by its unsigned-varint
// byte length. Serialization completes before any record bytes are written.
void WriteRecord(std::ostream& output,
                 const google::protobuf::MessageLite& message,
                 std::size_t max_record_bytes = kDefaultMaxRecordBytes);

// Reads one record and parses it into message. Returns false only for clean EOF
// between records; malformed, truncated, oversized, or invalid protobuf data
// throws ProtocolError.
bool ReadRecord(std::istream& input, google::protobuf::MessageLite& message,
                std::size_t max_record_bytes = kDefaultMaxRecordBytes);

} // namespace flang_dumper::protocol

#endif // FLANG_DUMPER_PROTOCOL_FRAMING_HPP
