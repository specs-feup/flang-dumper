#ifndef FLANG_DUMPER_PROTOCOL_GRAPH_IDS_HPP
#define FLANG_DUMPER_PROTOCOL_GRAPH_IDS_HPP

#include <cstddef>
#include <cstdint>
#include <unordered_map>

namespace flang_dumper::protocol {

// Assigns stable IDs to object identities during a prewalk, then checks that
// the emission walk visits those objects once and in ID order.
class GraphIds final {
public:
  GraphIds() = default;

  GraphIds(const GraphIds&) = delete;
  GraphIds& operator=(const GraphIds&) = delete;
  GraphIds(GraphIds&&) = delete;
  GraphIds& operator=(GraphIds&&) = delete;

  // Reserves an ID for pointer. Repeated reservations return the original ID.
  // Once frozen, only pointers already in the map may be reserved.
  std::uint64_t Reserve(const void* pointer);

  // Returns the ID assigned to pointer, or throws if it is null or unknown.
  std::uint64_t Lookup(const void* pointer) const;

  // Completes the prewalk and prevents reservations for new pointers.
  void Freeze() noexcept;

  // Records one object from the emission walk. Emissions must match the
  // reserved ID and follow reservation order.
  void VerifyEmission(const void* pointer, std::uint64_t actual_id);

  // Throws if an object reserved during the prewalk was not emitted.
  void Finish() const;

private:
  std::unordered_map<const void*, std::uint64_t> ids_;
  std::uint64_t next_id_ = 1;
  std::uint64_t next_emission_id_ = 1;
  std::size_t emitted_count_ = 0;
  bool frozen_ = false;
  bool id_space_exhausted_ = false;
  bool emission_ids_exhausted_ = false;
};

} // namespace flang_dumper::protocol

#endif // FLANG_DUMPER_PROTOCOL_GRAPH_IDS_HPP
