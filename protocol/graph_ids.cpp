#include "protocol/graph_ids.hpp"

#include <limits>
#include <stdexcept>

namespace flang_dumper::protocol {

std::uint64_t GraphIds::Reserve(const void* pointer) {
  if (pointer == nullptr) {
    throw std::invalid_argument("cannot reserve a null graph pointer");
  }

  const auto found = ids_.find(pointer);
  if (found != ids_.end()) {
    return found->second;
  }
  if (frozen_) {
    throw std::logic_error("cannot reserve a new pointer after GraphIds is frozen");
  }
  if (id_space_exhausted_) {
    throw std::overflow_error("graph ID space is exhausted");
  }

  const std::uint64_t id = next_id_;
  ids_.emplace(pointer, id);
  if (id == std::numeric_limits<std::uint64_t>::max()) {
    id_space_exhausted_ = true;
  } else {
    ++next_id_;
  }
  return id;
}

std::uint64_t GraphIds::Lookup(const void* pointer) const {
  if (pointer == nullptr) {
    throw std::invalid_argument("cannot look up a null graph pointer");
  }

  const auto found = ids_.find(pointer);
  if (found == ids_.end()) {
    throw std::out_of_range("graph pointer has no reserved ID");
  }
  return found->second;
}

void GraphIds::Freeze() noexcept { frozen_ = true; }

void GraphIds::VerifyEmission(const void* pointer, std::uint64_t actual_id) {
  if (pointer == nullptr) {
    throw std::invalid_argument("cannot emit a null graph pointer");
  }
  if (!frozen_) {
    throw std::logic_error("cannot verify graph emission before GraphIds is frozen");
  }
  if (emission_ids_exhausted_) {
    throw std::logic_error("all graph IDs have already been emitted");
  }

  const auto found = ids_.find(pointer);
  if (found == ids_.end()) {
    throw std::out_of_range("emitted graph pointer has no reserved ID");
  }
  if (actual_id != found->second) {
    throw std::invalid_argument("emitted graph ID does not match its reserved ID");
  }
  if (found->second != next_emission_id_) {
    throw std::logic_error("graph pointers must be emitted once in reserved ID order");
  }

  if (next_emission_id_ == std::numeric_limits<std::uint64_t>::max()) {
    // No ID can follow the final representable value.
    emission_ids_exhausted_ = true;
  } else {
    ++next_emission_id_;
  }
  ++emitted_count_;
}

void GraphIds::Finish() const {
  if (!frozen_) {
    throw std::logic_error("cannot finish graph emission before GraphIds is frozen");
  }
  if (ids_.size() != emitted_count_) {
    throw std::logic_error("not every reserved graph pointer was emitted");
  }
}

} // namespace flang_dumper::protocol
