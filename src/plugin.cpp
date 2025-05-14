#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"

using namespace Fortran::frontend;

// Visitor struct that defines Pre/Post functions for different types of nodes
struct ParseTreeVisitor {
public:
  template <typename A> bool Pre(const A &) const { return true; }
  template <typename A> void Post(const A &) const { return; }

  bool Pre(const Fortran::parser::Program &v) const {
    printf("\"%p\": {\n", &v);
    llvm::outs() << "\"type\": \"program\",\n";

    const auto &lst = v.v;

    llvm::outs() << "\"program-unit\": [\n";
    for (const auto &item : lst) {
      printf("\"%p\",\n", &item);
    }
    llvm::outs() << "],\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ProgramUnit &v) const {
    printf("\"%p\": {\n", &v);
    llvm::outs() << "\"type\": \"program-unit\",\n";

    const auto &var = v.u;

    std::visit([](auto &arg) { printf("\"value\": \"%p\",\n", &arg.value()); },
               var);

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::MainProgram &v) const {
    printf("\"%p\": {\n", &v);
    llvm::outs() << "\"type\": \"main-program\",\n";

    const auto &[program_stmt, specification_part, execution_part,
                 internal_subprogram_part, end_program_stmt] = v.t;

    printf("\"program-stmt\": \"%p\",\n", &program_stmt.value());
    printf("\"specification-part\": \"%p\",\n", &specification_part);
    printf("\"execution_part\": \"%p\",\n", &execution_part);
    printf("\"internal_subprogram_part\": \"%p\",\n",
           &internal_subprogram_part);
    printf("\"end-program-stmt\": \"%p\",\n", &end_program_stmt);

    llvm::outs() << "},\n";
    return true;
  }
};

class DumpAST : public PluginParseTreeAction {

  void executeAction() override {
    llvm::outs() << "{\n";
    ParseTreeVisitor visitor;
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
    llvm::outs() << "}\n";
  }
};

class DumpParseTreeAction : public PluginParseTreeAction {

  void executeAction() override {
    Fortran::parser::ParseTreeDumper visitor(llvm::outs());
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
  }
};

const static FrontendPluginRegistry::Add<DumpAST>
    X("dump-ast", "Dump all AST node data as a JSON object");
const static FrontendPluginRegistry::Add<DumpParseTreeAction>
    X2("dump-tree", "Run the ParseTreeDumper visitor on the code");
