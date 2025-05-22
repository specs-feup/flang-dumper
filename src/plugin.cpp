#include <llvm-20/llvm/Support/raw_ostream.h>
#include <optional>
#include <string>
#include <type_traits>
#include <variant>

#include "flang/Common/indirection.h"
#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"

#define DUMP_PROPERTY(KEY, VALUE)                                              \
  llvm::outs() << "\"" << KEY << "\": \"" << VALUE << "\",\n";

template <typename T, template <typename...> class Template>
struct is_specialization : std::false_type {};

template <typename... Args, template <typename...> class Template>
struct is_specialization<Template<Args...>, Template> : std::true_type {};

template <typename T> struct is_indirection : std::false_type {};

template <typename T, bool COPY>
struct is_indirection<Fortran::common::Indirection<T, COPY>> : std::true_type {
};

template <typename T> const char *getNodeName(const T &v) {
  if constexpr (is_specialization<T, Fortran::parser::Statement>::value) {
    return "Statement";
  } else {
    return Fortran::parser::ParseTreeDumper::GetNodeName(v);
  }
}

template <typename T> const char *getNodeName(const std::optional<T> &v) {
  if (v.has_value()) {
    return getNodeName(v.value());
  } else {
    return "null";
  }
}

template <typename T>
const char *getNodeName(const Fortran::common::Indirection<T> &v) {
  return getNodeName(v.value());
}

template <typename T> const char *getNodeName(const std::list<T> &v) {
  if (v.empty()) {
    return "list";
  } else {
    return getNodeName(v.front());
  }
}

template <typename T> std::string &getId(const T &v, const char *name) {
  std::ostringstream oss;
  oss << "0x" << std::hex << reinterpret_cast<uintptr_t>(&v) << "-" << name;
  static std::string id;
  id = oss.str();
  return id;
}

template <typename T> std::string getId(const T &v) {
  return getId(v, getNodeName(v));
}

template <typename T>
std::string getId(const Fortran::parser::Statement<T> &v) {
  return getId(v, "Statement");
}

template <typename T> std::string getId(const std::optional<T> &v) {
  if (v.has_value()) {
    return getId(v.value());
  } else {
    return getId(std::nullopt);
  }
}

template <typename T>
std::string getId(const Fortran::common::Indirection<T> &v) {
  return getId(v.value());
}

template <> std::string getId(const std::nullopt_t &) { return "null"; }

#define DUMP_NODE(CLASS, CONTENTS)                                             \
  bool Pre(const CLASS &v) const {                                             \
    llvm::outs() << "{\n";                                                     \
    DUMP_PROPERTY("id", getId(v))                                              \
                                                                               \
    CONTENTS;                                                                  \
                                                                               \
    llvm::outs() << "},\n";                                                    \
    return true;                                                               \
  }

auto variant_visitor = [](auto &value) {
  llvm::outs() << "\"" << getId(value) << "\"";
};

template <typename T> void dump(const T &v, const char *property_name) {
  llvm::outs() << "\"" << property_name << "\": \"" << getId(v) << "\",\n";
}

void dump(const char *v, const char *property_name) {
  llvm::outs() << "\"" << property_name << "\": \"" << v << "\",\n";
}

template <> void dump(const std::string &v, const char *property_name) {
  dump(v.c_str(), property_name);
}

template <>
void dump(const Fortran::parser::CharBlock &v, const char *property_name) {
  dump(v.ToString(), property_name);
}

template <> void dump(const std::nullopt_t &v, const char *property_name) {}

template <typename T>
void dump(const std::list<T> &v, const char *property_name) {
  if (!strcmp(property_name, "list")) {
    return;
  }

  llvm::outs() << "\"" << property_name << "\": [\n";
  for (const auto &item : v) {
    llvm::outs() << "\"" << getId(item) << "\",\n";
  }
  llvm::outs() << "],\n";
}

template <typename T>
void dump(const Fortran::parser::Statement<T> &v, const char *property_name) {
  llvm::outs() << "\"" << property_name << "<" << getNodeName(v.statement)
               << ">\": \"" << getId(v) << "\",\n";
}

template <typename... T>
void dump(const std::variant<T...> &v, const char *property_name = "value") {
  llvm::outs() << "\"" << property_name << "\": ";
  std::visit(variant_visitor, v);
  llvm::outs() << ",\n";
}

template <typename T>
void dump(const Fortran::common::Indirection<T> &v, const char *property_name) {
  dump(v.value(), property_name);
}

template <typename T>
void dump(const std::optional<T> &v, const char *property_name) {
  if (v.has_value()) {
    dump(v.value(), property_name);
  } else {
    dump(std::nullopt, property_name);
  }
}

template <typename... T> void dump(const std::tuple<T...> &v) {
  // For each element in the tuple, call dump
  std::apply([](const auto &...e) { ((dump(e, getNodeName(e))), ...); }, v);
}

// Visitor struct that defines Pre/Post functions for different types of nodes
struct ParseTreeVisitor {
public:
  template <typename A> bool Pre(const A &) const { return true; }
  template <typename A> void Post(const A &) const { return; }

  DUMP_NODE(Fortran::parser::Program, { dump(v.v, "ProgramUnit"); })

  DUMP_NODE(Fortran::parser::ProgramUnit, { dump(v.u); })

  DUMP_NODE(Fortran::parser::MainProgram, { dump(v.t); })

  DUMP_NODE(Fortran::parser::SpecificationPart, { dump(v.t); })

  DUMP_NODE(Fortran::parser::Block, { dump(v, "ExecutionPartConstruct"); })

  DUMP_NODE(Fortran::parser::InternalSubprogramPart, { dump(v.t); })

  DUMP_NODE(Fortran::parser::ExecutionPartConstruct, { dump(v.u); })

  DUMP_NODE(Fortran::parser::ExecutableConstruct, { dump(v.u); })

  template <typename T> bool Pre(const Fortran::parser::Statement<T> &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v)
                 << "-Statement" << "\",\n";

    llvm::outs() << "\"statement\": \""
                 << static_cast<const void *>(&v.statement) << "\",\n";
    llvm::outs() << "\"label\": \"" << static_cast<const void *>(&v.label)
                 << "\",\n";
    llvm::outs() << "\"source\": \"" << v.source << "\",\n";

    llvm::outs() << "},\n";
    return true;
  }

  DUMP_NODE(Fortran::parser::EndProgramStmt,
            { dump(v.v.value().ToString(), "name"); })

  DUMP_NODE(Fortran::parser::ActionStmt, { dump(v.u); })

  DUMP_NODE(Fortran::parser::PrintStmt, { dump(v.t); })
};

class DumpAST : public Fortran::frontend::PluginParseTreeAction {

  void executeAction() override {
    llvm::outs() << "{\"nodes\": [\n";
    ParseTreeVisitor visitor;
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
    llvm::outs() << "]}\n";
  }
};

class DumpParseTreeAction : public Fortran::frontend::PluginParseTreeAction {

  void executeAction() override {
    Fortran::parser::ParseTreeDumper visitor(llvm::outs());
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
  }
};

const static Fortran::frontend::FrontendPluginRegistry::Add<DumpAST>
    X("dump-ast", "Dump all AST node data as a JSON object");
const static Fortran::frontend::FrontendPluginRegistry::Add<DumpParseTreeAction>
    X2("dump-tree", "Run the ParseTreeDumper visitor on the code");
