#include "protocol/framing.hpp"

#include <cstdint>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>

#include "framing_test.pb.h"

namespace {

using flang_dumper::protocol::ProtocolError;
using flang_dumper::protocol::ReadHeader;
using flang_dumper::protocol::ReadRecord;
using flang_dumper::protocol::WriteHeader;
using flang_dumper::protocol::WriteRecord;
using flang_dumper::protocol::test::TinyRecord;

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

std::string HeaderBytes() {
  std::ostringstream output(std::ios::binary);
  WriteHeader(output);
  return output.str();
}

void TestHeaderEncodingAndRoundTrip() {
  const std::string header = HeaderBytes();
  Check(header.size() == 12, "header must contain 12 bytes");
  Check(header.substr(0, 8) == "FLASTPB1", "header magic bytes differ");
  Check(static_cast<unsigned char>(header[8]) == 1 && header[9] == 0 &&
            header[10] == 0 && header[11] == 0,
        "version must be little-endian uint32 value 1");

  std::stringstream stream(std::ios::in | std::ios::out | std::ios::binary);
  WriteHeader(stream);
  TinyRecord first;
  first.set_id(7);
  first.set_text("first record");
  TinyRecord second;
  second.set_id(19);
  WriteRecord(stream, first);
  WriteRecord(stream, second);

  stream.seekg(0);
  ReadHeader(stream);
  TinyRecord decoded;
  Check(ReadRecord(stream, decoded), "first record should be present");
  Check(decoded.id() == 7 && decoded.text() == "first record",
        "first record did not round-trip");
  Check(ReadRecord(stream, decoded), "second record should be present");
  Check(decoded.id() == 19 && !decoded.has_text(),
        "second record did not round-trip");
  Check(!ReadRecord(stream, decoded), "EOF between records should be clean");

  std::istringstream empty(std::string{}, std::ios::binary);
  Check(!ReadRecord(empty, decoded), "empty record stream should be clean EOF");
}

void TestBadHeaders() {
  std::string wrong_magic = HeaderBytes();
  wrong_magic[2] = 'X';
  std::istringstream bad_magic(wrong_magic, std::ios::binary);
  ExpectProtocolError([&] { ReadHeader(bad_magic); }, "wrong magic");

  std::string wrong_version = HeaderBytes();
  wrong_version[8] = 2;
  std::istringstream bad_version(wrong_version, std::ios::binary);
  ExpectProtocolError([&] { ReadHeader(bad_version); }, "wrong version");

  std::istringstream truncated(HeaderBytes().substr(0, 11), std::ios::binary);
  ExpectProtocolError([&] { ReadHeader(truncated); }, "truncated header");
}

void TestBadRecords() {
  TinyRecord decoded;

  std::istringstream zero_length(std::string("\0", 1), std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(zero_length, decoded); }, "zero length");

  std::istringstream truncated_varint(std::string("\x80", 1), std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(truncated_varint, decoded); },
                      "truncated varint");

  std::istringstream overflow(std::string("\xff\xff\xff\xff\x10", 5),
                              std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(overflow, decoded); }, "varint overflow");

  std::istringstream too_long(std::string("\x80\x80\x80\x80\x80", 5),
                              std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(too_long, decoded); }, "too-long varint");

  std::istringstream noncanonical(std::string("\x81\0", 2), std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(noncanonical, decoded); },
                      "non-canonical varint");

  std::istringstream truncated_payload(std::string("\x03\x08\x01", 3),
                                       std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(truncated_payload, decoded); },
                      "truncated payload");

  std::istringstream over_limit(std::string("\x64", 1), std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(over_limit, decoded, 16); },
                      "record above configured maximum");

  // A one-byte protobuf payload with field number zero is malformed.
  std::istringstream invalid_protobuf(std::string("\x01\x0f", 2),
                                      std::ios::binary);
  ExpectProtocolError([&] { ReadRecord(invalid_protobuf, decoded); },
                      "invalid protobuf payload");
}

void TestWriterFailures() {
  TinyRecord oversized;
  oversized.set_id(1);
  oversized.set_text("payload larger than one byte");
  std::ostringstream output(std::ios::binary);
  ExpectProtocolError([&] { WriteRecord(output, oversized, 1); },
                      "writer maximum");
  Check(output.str().empty(), "oversized write must not emit a partial record");

  TinyRecord uninitialized;
  uninitialized.set_text("missing required id");
  ExpectProtocolError([&] { WriteRecord(output, uninitialized); },
                      "serialization failure");
  Check(output.str().empty(), "serialization failure must not emit a record");
}

} // namespace

int main() {
  try {
    TestHeaderEncodingAndRoundTrip();
    TestBadHeaders();
    TestBadRecords();
    TestWriterFailures();
  } catch (const std::exception& error) {
    std::cerr << "framing tests failed: " << error.what() << '\n';
    return 1;
  }

  std::cout << "framing tests passed\n";
  return 0;
}
