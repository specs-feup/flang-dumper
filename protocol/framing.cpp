#include "protocol/framing.hpp"

#include <array>
#include <istream>
#include <limits>
#include <ostream>
#include <string>

namespace flang_dumper::protocol {
namespace {

constexpr std::array<unsigned char, 8> kMagic{{'F', 'L', 'A', 'S', 'T', 'P', 'B', '1'}};
constexpr std::size_t kHeaderSize = 12;

void WriteBytes(std::ostream& output, const char* bytes, std::size_t size,
                const char* context) {
  output.write(bytes, static_cast<std::streamsize>(size));
  if (!output) {
    throw ProtocolError(std::string("failed to write ") + context);
  }
}

void ReadBytes(std::istream& input, char* bytes, std::size_t size,
               const char* context) {
  input.read(bytes, static_cast<std::streamsize>(size));
  if (input.gcount() != static_cast<std::streamsize>(size)) {
    throw ProtocolError(std::string("truncated ") + context);
  }
  if (!input) {
    throw ProtocolError(std::string("failed to read ") + context);
  }
}

void WriteVarint32(std::ostream& output, std::uint32_t value) {
  std::array<char, 5> bytes{};
  std::size_t count = 0;
  do {
    unsigned char byte = static_cast<unsigned char>(value & 0x7fu);
    value >>= 7u;
    if (value != 0) {
      byte = static_cast<unsigned char>(byte | 0x80u);
    }
    bytes[count++] = static_cast<char>(byte);
  } while (value != 0);
  WriteBytes(output, bytes.data(), count, "record length");
}

int GetRequiredByte(std::istream& input, const char* context) {
  const auto byte = input.get();
  if (byte == std::char_traits<char>::eof()) {
    throw ProtocolError(std::string("truncated ") + context);
  }
  return std::char_traits<char>::to_char_type(byte) & 0xff;
}

std::size_t EncodedVarintSize(std::uint32_t value) {
  std::size_t count = 1;
  while (value >= 0x80u) {
    value >>= 7u;
    ++count;
  }
  return count;
}

std::uint32_t ReadVarint32(std::istream& input, unsigned char first_byte) {
  std::uint32_t value = 0;
  unsigned char byte = first_byte;

  for (unsigned int index = 0; index < 5; ++index) {
    if (index != 0) {
      byte = static_cast<unsigned char>(GetRequiredByte(input, "record length"));
    }

    // A uint32 varint has only four useful bits in its fifth byte. This also
    // rejects a continuation bit in byte five, before any payload is read.
    if (index == 4 && (byte & 0xf0u) != 0) {
      throw ProtocolError("record length varint overflows uint32");
    }

    value |= static_cast<std::uint32_t>(byte & 0x7fu) << (7u * index);
    if ((byte & 0x80u) == 0) {
      if (EncodedVarintSize(value) != index + 1) {
        throw ProtocolError("record length varint is not canonical");
      }
      return value;
    }
  }

  throw ProtocolError("record length varint is too long");
}

} // namespace

void WriteHeader(std::ostream& output) {
  std::array<char, kHeaderSize> header{};
  for (std::size_t index = 0; index < kMagic.size(); ++index) {
    header[index] = static_cast<char>(kMagic[index]);
  }
  header[8] = static_cast<char>(kProtocolVersion & 0xffu);
  header[9] = static_cast<char>((kProtocolVersion >> 8u) & 0xffu);
  header[10] = static_cast<char>((kProtocolVersion >> 16u) & 0xffu);
  header[11] = static_cast<char>((kProtocolVersion >> 24u) & 0xffu);
  WriteBytes(output, header.data(), header.size(), "protocol header");
}

void ReadHeader(std::istream& input) {
  std::array<unsigned char, kHeaderSize> header{};
  ReadBytes(input, reinterpret_cast<char*>(header.data()), header.size(),
            "protocol header");

  for (std::size_t index = 0; index < kMagic.size(); ++index) {
    if (header[index] != kMagic[index]) {
      throw ProtocolError("invalid protocol magic");
    }
  }

  const std::uint32_t version =
      static_cast<std::uint32_t>(header[8]) |
      (static_cast<std::uint32_t>(header[9]) << 8u) |
      (static_cast<std::uint32_t>(header[10]) << 16u) |
      (static_cast<std::uint32_t>(header[11]) << 24u);
  if (version != kProtocolVersion) {
    throw ProtocolError("unsupported protocol version");
  }
}

void WriteRecord(std::ostream& output,
                 const google::protobuf::MessageLite& message,
                 std::size_t max_record_bytes) {
  const std::size_t serialized_size = message.ByteSizeLong();
  if (serialized_size == 0) {
    throw ProtocolError("zero-length protobuf records are not allowed");
  }
  if (serialized_size > max_record_bytes ||
      serialized_size > std::numeric_limits<std::uint32_t>::max()) {
    throw ProtocolError("protobuf record exceeds configured maximum");
  }
  if (!message.IsInitialized()) {
    throw ProtocolError("protobuf message is missing required fields");
  }

  std::string payload;
  if (!message.SerializeToString(&payload)) {
    throw ProtocolError("protobuf serialization failed");
  }
  if (payload.size() != serialized_size) {
    throw ProtocolError("protobuf serialized size changed during serialization");
  }

  WriteVarint32(output, static_cast<std::uint32_t>(payload.size()));
  WriteBytes(output, payload.data(), payload.size(), "protobuf record");
}

bool ReadRecord(std::istream& input, google::protobuf::MessageLite& message,
                std::size_t max_record_bytes) {
  const auto first_byte = input.get();
  if (first_byte == std::char_traits<char>::eof()) {
    if (input.eof() && !input.bad()) {
      return false;
    }
    throw ProtocolError("failed to read record length");
  }

  const auto length = ReadVarint32(
      input, static_cast<unsigned char>(std::char_traits<char>::to_char_type(first_byte)));
  if (length == 0) {
    throw ProtocolError("zero-length protobuf records are not allowed");
  }
  if (static_cast<std::size_t>(length) > max_record_bytes) {
    throw ProtocolError("protobuf record exceeds configured maximum");
  }

  std::string payload(static_cast<std::size_t>(length), '\0');
  ReadBytes(input, payload.data(), payload.size(), "protobuf record payload");
  if (!message.ParseFromString(payload)) {
    throw ProtocolError("protobuf parsing failed");
  }
  return true;
}

} // namespace flang_dumper::protocol
