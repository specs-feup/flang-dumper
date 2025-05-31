#ifndef __COLLECTOR_H__
#define __COLLECTOR_H__

#include <functional>
#include <vector>

#define CONCAT_(a, b) a##b
#define CONCAT(a, b) CONCAT_(a, b)

// === Collector class ===

template <typename Owner> struct Collector {
  static inline std::vector<std::function<void()>> registry;

  template <typename T> struct Registrar {
    Registrar() {
      Collector<Owner>::registry.emplace_back(
          [] { Owner::template dump_enum<T>(); });
    }
  };

  static void for_each() {
    for (auto &fn : registry) {
      fn(); // Call each registered function
    }
  }
};

#define REGISTER_TYPE(CLASS)                                                   \
  static inline typename Collector<ThisClass>::Registrar<CLASS> CONCAT(        \
      _registrar_, __COUNTER__)

#endif // __COLLECTOR_H__
