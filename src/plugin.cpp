#include <sstream>
#include <type_traits>
#include <iomanip>

#include <llvm/Support/raw_ostream.h>

#include "flang/Support/Fortran.h"
#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"
#include "flang/Parser/provenance.h"
#include "flang/Semantics/symbol.h"
#include "flang/Semantics/scope.h"

#include "plugin.h"
#include "comments.h"

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
  } else if constexpr (is_specialization<
                           T, Fortran::parser::UnlabeledStatement>::value) {
    return "UnlabeledStatement";
  } else if constexpr (is_specialization<T, Fortran::parser::Scalar>::value
                    || is_specialization<T, Fortran::parser::Constant>::value
                    || is_specialization<T, Fortran::parser::Integer>::value
                    || is_specialization<T, Fortran::parser::Logical>::value) {
    return "Expr";
  } else if constexpr (is_specialization<T,
                                         Fortran::parser::DefaultChar>::value) {
    return "DefaultChar";
  } else if constexpr (std::is_same_v<T, Fortran::parser::CharBlock>) {
    return "CharBlock";
  } else if constexpr (std::is_same_v<T, Fortran::parser::CommonStmt::Block>) {
    return "CommonStmtBlock";  // To prevent name conflicts with the other AST Block nodes
  } else {
    if constexpr (std::is_same_v<
                      decltype(Fortran::parser::ParseTreeDumper::GetNodeName(
                          v)),
                      std::string>) {
      static std::string name =
          Fortran::parser::ParseTreeDumper::GetNodeName(v);
      return name.c_str();
    } else {
      return Fortran::parser::ParseTreeDumper::GetNodeName(v);
    }
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

struct variant_visitor {
  template <typename T> void operator()(const T &value) const {
    const char *valueName = getNodeName(value);

    dump(valueName, "variantKey");
    dump(value, valueName);
  }
};

template <typename T> void dump(const T &v, const char *property_name) {
  DUMP_PROPERTY(property_name, getId(v));
}

void dump(const char *v, const char *property_name) {
  dump(v ? std::string_view{v} : std::string_view{}, property_name);
}

void dump(const bool v, const char *property_name) {
    DUMP_PROPERTY(property_name, v);
}

void dump(std::string_view v, const char *property_name) {
  DUMP_PROPERTY(property_name, escape_quotes(v));
}

std::string escape_quotes(std::string_view sv) {
    std::string out;
    out.reserve(sv.size());

    for (char c : sv) {
        if (c == '"')
            out += "\\\"";
        else
            out += c;
    }
    return out;
}

template <typename T>
void dump(const Fortran::parser::Scalar<T> &v, const char *property_name) {
    dump(v.thing, property_name);
}

template <typename T>
void dump(const Fortran::parser::Logical<T> &v, const char *property_name) {
    dump(v.thing, property_name);
}

template <typename T>
void dump(const Fortran::parser::Integer<T> &v, const char *property_name) {
    dump(v.thing, property_name);
}

template <typename T>
void dump(const Fortran::parser::Constant<T> &v, const char *property_name) {
    dump(v.thing, property_name);
}

template <typename T>
void dump(const Fortran::parser::DefaultChar<T> &v, const char *property_name) {
  dump(v.thing, property_name);
}

void dump(const Fortran::parser::Sign &v, const char *property_name) {
    switch(v) {
        case Fortran::parser::Sign::Positive:
            dump("positive", property_name);
            break;
        case Fortran::parser::Sign::Negative:
            dump("negative", property_name);
            break;
    }
}

template <> void dump(const std::uint64_t &v, const char *property_name) {
  DUMP_PROPERTY(property_name, v);
}

template <> void dump(const std::int64_t &v, const char *property_name) {
  DUMP_PROPERTY(property_name, v);
}

template <> void dump(const int &v, const char *property_name) {
  DUMP_PROPERTY(property_name, v);
}

template <> void dump(const std::string &v, const char *property_name) {
  dump(std::string_view{v}, property_name);
}

template <>
void dump(const Fortran::parser::CharBlock &v, const char *property_name) {
  dump(v.ToString(), property_name);
}

template <> void dump(const std::nullopt_t &v, const char *property_name) {
  // No need to dump anything
}

template <typename T>
void dump(const std::list<T> &v, const char *property_name) {
  if (!strcmp(property_name, "list")) {
    return;
  }
  bool first = true;

  llvm::outs() << ",\n\"" << property_name << "\": [\n";
  for (const auto &item : v) {
    if (!first) {
      llvm::outs() << ",\n";
    } else {
      first = false;
    }
    llvm::outs() << "\"" << getId(item) << "\"";
  }
  llvm::outs() << "]";
}

template <typename T>
void dump(const Fortran::parser::Statement<T> &v, const char *property_name) {
  DUMP_PROPERTY(property_name << "<" << getNodeName(v.statement) << ">",
                getId(v));
}

template <typename T> void dump(const Fortran::parser::Statement<T> &v) {
  DUMP_PROPERTY(getNodeName(v) << "<" << getNodeName(v.statement) << ">",
                getId(v));
}

template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v,
          const char *property_name) {
  DUMP_PROPERTY(property_name << "<" << getNodeName(v.statement) << ">",
                getId(v));
}

template <typename T>
void dump(const Fortran::parser::UnlabeledStatement<T> &v) {
  DUMP_PROPERTY(getNodeName(v) << "<" << getNodeName(v.statement) << ">",
                getId(v));
}

template <typename... T>
void dump(const std::variant<T...> &v, const char *property_name) {
  std::visit(variant_visitor{}, v);
}

template <typename T>
void dump(const Fortran::common::Indirection<T> &v, const char *property_name) {
  dump(v.value(), property_name);
}


template <typename T>
void dump(const Fortran::common::Indirection<T> &v) {
  dump(v.value());
}


void dump(const Fortran::parser::Expr &v) {
  dump(v.u);
}

template <typename T>
void dump(const std::optional<T> &v, const char *property_name) {
  if (v.has_value()) {
    dump(v.value(), property_name);
  } else {
    dump(std::nullopt, property_name);
  }
}

void dump(const Fortran::semantics::Scope &scope, const char *property_name) {
  dump(Fortran::semantics::Scope::EnumToString(scope.kind()), property_name);
}


template <typename... T> void dump(const std::tuple<T...> &v) {
  // For each element in the tuple, call dump
  std::apply([](const auto &...e) { ((dump(e, getNodeName(e))), ...); }, v);
}

// Visitor struct that defines Pre/Post functions for different types of nodes
struct ParseTreeVisitor {
public:
  using ThisClass = ParseTreeVisitor;

  ParseTreeVisitor(
    const Fortran::parser::AllSources &allSources,
    const Fortran::parser::AllCookedSources &allCooked,
    std::vector<RawComment> &&rawComments
) : allCooked(allCooked), allSources(allSources), rawComments(std::move(rawComments)) {}

  std::vector<Comment> &getComments() { return comments; }

  template <typename A> bool Pre(const A &) { return true; }
  template <typename A> void Post(const A &) { return; }

  // Function to dump all registered enums as JSON
  static void dumpEnumValues() {
    const auto &reg = Collector<ThisClass>::get_registry();
    bool first = true;
    for (const auto &[name, func] : reg) {
      if (!first)
        llvm::outs() << ",\n";
      llvm::outs() << "  \"" << name << "\": ";
      func();
      first = false;
    }
    llvm::outs() << "\n";
  }


  template <typename T> static void dump_enum() {
    // llvm::outs() << T::name() << ": " << T::value() << '\n';
  }

  std::optional<size_t> getLine(const Fortran::parser::CharBlock &block) {
    auto range = allCooked.GetSourcePositionRange(block);
    return range.has_value()
      ? std::optional<size_t>(range->first.line)
      : std::nullopt;
  }

  void flushComments() {
    while (comments.size() < rawComments.size()) {
      size_t commentIndex = comments.size();

      Comment comment = processComment(rawComments[commentIndex], programId, 0);
      comments.push_back(comment);
      commentIndex++;
    }
  }

  void flushComments(const std::string &stmtId, std::size_t stmtLine) {
    while (comments.size() < rawComments.size()) {
      size_t commentIndex = comments.size();

      if (rawComments[commentIndex].line < stmtLine
        || (rawComments[commentIndex].line == stmtLine && rawComments[commentIndex].sepsBefore == 0)) {
        Comment comment = processComment(rawComments[commentIndex], stmtId, stmtLine);
        comments.push_back(comment);
      } else if (rawComments[commentIndex].line == stmtLine && rawComments[commentIndex].sepsBefore > 0) {
        rawComments[commentIndex].sepsBefore--;
        break;
      } else {
        break;
      }
    }
  }

  template <typename T>
  bool Pre(const Fortran::parser::Statement<T> &v) {
    std::string stmtId = getId(v);
    if (auto line = getLine(v.source)) {
      flushComments(stmtId, *line);
    }

    DUMP_BARE_NODE({
      dump(v.statement, "statement");
      dump(v.label, "label");
      dump(v.source, "source");
    })
  }

  template <typename T>
  bool Pre(const Fortran::parser::UnlabeledStatement<T> &v) {
    DUMP_BARE_NODE({
      dump(v.statement, "statement");
      dump(v.source, "source");
    })
  }

  std::string controlEditDesc_toString(Fortran::format::ControlEditDesc::Kind k) {
    using Kind = Fortran::format::ControlEditDesc::Kind;
    switch (k) {
        case Kind::T:         return "T";
        case Kind::TL:        return "TL";
        case Kind::TR:        return "TR";
        case Kind::X:         return "X";
        case Kind::Slash:     return "Slash";
        case Kind::Colon:     return "Colon";
        case Kind::SS:        return "SS";
        case Kind::SP:        return "SP";
        case Kind::S:         return "S";
        case Kind::P:         return "P";
        case Kind::BN:        return "BN";
        case Kind::BZ:        return "BZ";
        case Kind::RU:        return "RU";
        case Kind::RD:        return "RD";
        case Kind::RZ:        return "RZ";
        case Kind::RN:        return "RN";
        case Kind::RC:        return "RC";
        case Kind::RP:        return "RP";
        case Kind::DC:        return "DC";
        case Kind::DP:        return "DP";
        case Kind::Dollar:    return "Dollar";
        case Kind::Backslash: return "Backslash";
        default:              return "Unknown";
    }
}

#include "generated_visitor_registrations.inc"

private:
  bool firstNodeDump = true;
  std::string programId;
  std::vector<Comment> comments;

  const Fortran::parser::AllCookedSources& allCooked;
  const Fortran::parser::AllSources& allSources;
  std::vector<RawComment> rawComments;
};

class DumpAST : public Fortran::frontend::PluginParseTreeAction {

  void executeAction() override {
    const Fortran::parser::AllCookedSources &allCooked = getParsing().allCooked();
    const Fortran::parser::AllSources &allSources = allCooked.allSources();

    // Extract comments
    std::vector<RawComment> rawComments;
    if (auto maybeFirst = allSources.GetFirstFileProvenance()) {
      if (const auto *sourceFile = allSources.GetSourceFile(maybeFirst->start())) {
        rawComments = extractComments(*sourceFile);
      }
    }

    llvm::outs() << "{\"nodes\": [\n";
    ParseTreeVisitor visitor(allSources, allCooked, std::move(rawComments));
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
    visitor.flushComments();
    llvm::outs() << "],\n";

    llvm::outs() << "\"comments\": [\n";
    for (const auto &comment : visitor.getComments()) {
      llvm::outs() << toString(comment);
      if (&comment != &visitor.getComments().back()) {
        llvm::outs() << ",\n";
      }
    }
    llvm::outs() << "],\n";

    llvm::outs() << "\"enums\": {\n";
    ParseTreeVisitor::dumpEnumValues();
    llvm::outs() << "}\n}\n";
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
