#pragma once

// These records exercise the generator interface only. They are not a copy of
// Flang declarations and do not define the production protobuf protocol.
namespace generator_fixture {

struct ComplexPair {
  float lane_0;
  float lane_1;
};

struct OptionalFloat {
  bool has_value;
  float value;
};

enum class ExpressionOperation : int {
  Add = 11,
  Multiply = 29,
};

struct Expression {
  ExpressionOperation operation;
  ComplexPair operands;
};

} // namespace generator_fixture
