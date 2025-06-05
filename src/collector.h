#ifndef __COLLECTOR_H__
#define __COLLECTOR_H__

#include <functional>
#include <vector>

#define CONCAT_(a, b) a##b
#define CONCAT(a, b) CONCAT_(a, b)

// === Collector class ===

template <typename Owner> struct Collector {
  using EnumDumpFunc = void (*)();
  static inline std::vector<std::pair<const char *, EnumDumpFunc>> registry;

  struct Registrar {
    Registrar(const char *name, EnumDumpFunc func) {
      Collector<Owner>::registry.emplace_back(name, func);
    }
  };

  // No output/printing here; just data collection.
  static const auto &get_registry() { return registry; }
};

#define REGISTER_TYPE(CLASS)                                                   \
  static inline typename Collector<ThisClass>::Registrar<CLASS> CONCAT(        \
      _registrar_, __COUNTER__)

#endif // __COLLECTOR_H__
