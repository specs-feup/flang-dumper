#include "protocol/graph_ids.hpp"

#include <cstdint>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>

namespace {

using flang_dumper::protocol::GraphIds;

void Check(bool condition, const std::string& message) {
  if (!condition) {
    throw std::runtime_error(message);
  }
}

template <typename Exception, typename Function>
void ExpectThrows(Function&& function, const std::string& test_name) {
  try {
    function();
  } catch (const Exception&) {
    return;
  }
  throw std::runtime_error(test_name + ": expected exception");
}

void TestPrewalkIDsAndForwardReference() {
  int root = 0;
  int child = 0;
  GraphIds ids;

  Check(ids.Reserve(&root) == 1, "first reserved pointer should receive ID 1");
  Check(ids.Reserve(&child) == 2, "second reserved pointer should receive ID 2");
  Check(ids.Lookup(&child) == 2,
        "prewalk should allow looking up a child before it is emitted");
  Check(ids.Reserve(&root) == 1, "repeated reservation should keep the original ID");

  ids.Freeze();
  Check(ids.Reserve(&child) == 2,
        "repeated known-pointer reservation should work after freezing");
  ids.VerifyEmission(&root, 1);
  ids.VerifyEmission(&child, 2);
  ids.Finish();
}

void TestNullAndUnknownPointers() {
  int known = 0;
  int unknown = 0;
  GraphIds ids;

  ExpectThrows<std::invalid_argument>([&] { ids.Reserve(nullptr); }, "null reservation");
  ExpectThrows<std::invalid_argument>([&] { ids.Lookup(nullptr); }, "null lookup");
  ExpectThrows<std::out_of_range>([&] { ids.Lookup(&unknown); }, "unknown lookup");
  Check(ids.Reserve(&known) == 1, "known pointer should receive an ID after failures");
}

void TestFreezeRejectsNewPointers() {
  int known = 0;
  int unknown = 0;
  GraphIds ids;
  ids.Reserve(&known);
  ids.Freeze();

  ExpectThrows<std::logic_error>([&] { ids.Reserve(&unknown); }, "frozen reservation");
  Check(ids.Reserve(&known) == 1, "frozen known-pointer reservation should be idempotent");
}

void TestEmissionChecksAndRecovery() {
  int root = 0;
  int child = 0;
  int unknown = 0;
  GraphIds ids;
  ids.Reserve(&root);
  ids.Reserve(&child);
  ids.Freeze();

  ExpectThrows<std::logic_error>([&] { ids.VerifyEmission(&child, 2); },
                                 "out-of-order emission");
  ExpectThrows<std::invalid_argument>([&] { ids.VerifyEmission(&root, 2); },
                                      "mismatched emitted ID");
  ExpectThrows<std::out_of_range>([&] { ids.VerifyEmission(&unknown, 3); },
                                  "unknown emitted pointer");
  ids.VerifyEmission(&root, 1);
  ExpectThrows<std::logic_error>([&] { ids.VerifyEmission(&root, 1); },
                                 "duplicate emission");
  ids.VerifyEmission(&child, 2);
  ids.Finish();
}

void TestFinishRequiresAllEmissions() {
  int first = 0;
  int second = 0;
  GraphIds ids;
  ids.Reserve(&first);
  ids.Reserve(&second);
  ids.Freeze();
  ids.VerifyEmission(&first, 1);

  ExpectThrows<std::logic_error>([&] { ids.Finish(); }, "missing emission");
  ids.VerifyEmission(&second, 2);
  ids.Finish();
}

void TestFinishRequiresFreeze() {
  GraphIds ids;
  ExpectThrows<std::logic_error>([&] { ids.Finish(); }, "finish before freeze");
  ids.Freeze();
  ids.Finish();
}

} // namespace

int main() {
  try {
    TestPrewalkIDsAndForwardReference();
    TestNullAndUnknownPointers();
    TestFreezeRejectsNewPointers();
    TestEmissionChecksAndRecovery();
    TestFinishRequiresAllEmissions();
    TestFinishRequiresFreeze();
    std::cout << "graph_ids_test: all checks passed\n";
  } catch (const std::exception& error) {
    std::cerr << "graph_ids_test: " << error.what() << '\n';
    return 1;
  }
  return 0;
}
