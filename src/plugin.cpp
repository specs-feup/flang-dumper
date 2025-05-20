#include <llvm-20/llvm/Support/raw_ostream.h>

#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"

// Visitor struct that defines Pre/Post functions for different types of nodes
struct ParseTreeVisitor {
public:
  template <typename A> bool Pre(const A &) const { return true; }
  template <typename A> void Post(const A &) const { return; }

  bool Pre(const Fortran::parser::ExecutionPartConstruct &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"execution-part-construct\",\n";

    llvm::outs() << "},\n";
    return true;
  }

  bool Pre(const Fortran::parser::ExecutableConstruct &v) const {
    llvm::outs() << "{\n";
    llvm::outs() << "\"id\": \"" << static_cast<const void *>(&v) << "\",\n";
    llvm::outs() << "\"type\": \"executable-construct\",\n";

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
