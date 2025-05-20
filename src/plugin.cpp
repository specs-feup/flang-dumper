#include <llvm-20/llvm/Support/raw_ostream.h>
#include <optional>
#include <type_traits>
#include <variant>

#include "flang/Common/indirection.h"
#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"

template <typename T, template <typename...> class Template>
struct is_specialization : std::false_type {};

template <typename... Args, template <typename...> class Template>
struct is_specialization<Template<Args...>, Template> : std::true_type {};

template <typename T> struct is_indirection : std::false_type {};

template <typename T, bool COPY>
struct is_indirection<Fortran::common::Indirection<T, COPY>> : std::true_type {
};

auto variant_visitor = [](auto &value) {
  using T = std::decay_t<decltype(value)>;

  llvm::outs() << "\"value\": ";

  if constexpr (std::is_same_v<T, std::nullopt_t>) {
    // Value is nullopt
    llvm::outs() << "\"null\"";
  } else if constexpr (is_specialization<T, std::optional>::value) {
    if (value.has_value()) {
      llvm::outs() << "\"" << static_cast<const void *>(&value.value()) << "\"";
    } else {
      // Optional is empty (nullptr)
      llvm::outs() << "\"null\"";
    }
  } else if constexpr (is_indirection<T>::value) {
    llvm::outs() << "\"" << static_cast<const void *>(&value.value()) << "\"";
  } else {
    llvm::outs() << "\"" << static_cast<const void *>(&value) << "\"";
  }

  llvm::outs() << ",\n";
};

// Visitor struct that defines Pre/Post functions for different types of nodes
struct ParseTreeVisitor {
public:
  template <typename A> bool Pre(const A &) const { return true; }
  template <typename A> void Post(const A &) const { return; }

  bool Pre(const Fortran::parser::Program &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"program\",\n";

    const auto &lst = v.v;

    llvm::outs() << "\"program-unit\": [\n";
    for (const auto &item : lst) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ProgramUnit &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"program-unit\",\n";

    const auto &var = v.u;

    std::visit(variant_visitor, var);

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::MainProgram &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"main-program\",\n";

    const auto &[program_stmt, specification_part, execution_part,
                 internal_subprogram_part, end_program_stmt] = v.t;

    llvm::outs() << "\"program-stmt\": \""
                 << static_cast<const void *>(&program_stmt.value()) << "\",\n";
    llvm::outs() << "\"specification-part\": \""
                 << static_cast<const void *>(&specification_part) << "\",\n";
    llvm::outs() << "\"execution-part\": \""
                 << static_cast<const void *>(&execution_part) << "\",\n";
    llvm::outs() << "\"internal-subprogram-part\": \""
                 << static_cast<const void *>(&internal_subprogram_part)
                 << "\",\n";
    llvm::outs() << "\"end-program-stmt\": \""
                 << end_program_stmt.statement.v->ToString() << "\",\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::SpecificationPart &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"specification-part\",\n";

    const auto &[OpenACCDeclarativeConstructs, OpenMPDeclarativeConstructs,
                 CompilerDirectives, UseStmts, ImportStmts, ImplicitPart,
                 DeclarationConstructs] = v.t;

    llvm::outs() << "\"OpenACCDeclarativeConstructs\": [\n";
    for (const auto &item : OpenACCDeclarativeConstructs) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"OpenMPDeclarativeConstructs\": [\n";
    for (const auto &item : OpenMPDeclarativeConstructs) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"CompilerDirectives\": [\n";
    for (const auto &item : CompilerDirectives) {
      llvm::outs() << "\"" << static_cast<const void *>(&item.value())
                   << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"UseStmts\": [\n";
    for (const auto &item : UseStmts) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"ImportStmts\": [\n";
    for (const auto &item : ImportStmts) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"ImplicitPart\": \""
                 << static_cast<const void *>(&ImplicitPart) << "\",\n";

    llvm::outs() << "\"DeclarationConstructs\": [\n";
    for (const auto &item : DeclarationConstructs) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::Block &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"block\",\n";

    llvm::outs() << "\"ExecutionPartConstruct\": [\n";
    for (const auto &item : v) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::InternalSubprogramPart &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"internal-subprogram-part\",\n";

    const auto &[contains_stmt, InternalSubprograms] = v.t;

    llvm::outs() << "\"contains-stmt\": \""
                 << static_cast<const void *>(&contains_stmt) << "\",\n";

    llvm::outs() << "\"InternalSubprograms\": [\n";
    for (const auto &item : InternalSubprograms) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "],\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::EndProgramStmt &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"end-program-stmt\",\n";

    const auto &var = v.v.value();
    llvm::outs() << "\"name\": \"" << var.ToString() << "\",\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ExecutionPartConstruct &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"execution-part-construct\",\n";

    const auto &var = v.u;
    std::visit(variant_visitor, var);

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ExecutableConstruct &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"executable-construct\",\n";

    const auto &var = v.u;
    std::visit(variant_visitor, var);

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ActionStmt &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"action-stmt\",\n";

    const auto &var = v.u;
    std::visit(variant_visitor, var);

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::PrintStmt &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"print-stmt\",\n";

    const auto &[format, output_items] = v.t;

    llvm::outs() << "\"format\": \"" << static_cast<const void *>(&format)
                 << "\",\n";

    llvm::outs() << "\"output-items\": [\n";
    for (const auto &item : output_items) {
      llvm::outs() << "\"" << static_cast<const void *>(&item) << "\",\n";
    }
    llvm::outs() << "]\n";

    llvm::outs() << "},\n";
    return true;
  }
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
