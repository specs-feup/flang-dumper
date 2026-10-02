#include <cstddef>
#include <cstdint>
#include <iostream>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"
#include "flang/Parser/parsing.h"
#include "flang/Parser/provenance.h"

#include "binary_fields.hpp"
#include "comments.h"
#include "protocol/ast_kinds.hpp"
#include "protocol/binary_context.hpp"
#include "protocol/template_kinds.hpp"

namespace {

using flang_dumper::binary::FieldEncoder;
using flang_dumper::binary::IdentityOf;
using flang_dumper::binary::NodeName;
using flang_dumper::protocol::BinaryContext;

class BinaryParseTreeVisitor final {
public:
  BinaryParseTreeVisitor(
      BinaryContext& context,
      const Fortran::parser::AllSources& allSources,
      const Fortran::parser::AllCookedSources& allCooked,
      std::vector<RawComment>&& rawComments)
      : context_{context}, fields_{context}, allSources_{allSources},
        allCooked_{allCooked}, rawComments_{std::move(rawComments)} {}

  void BeginPrewalk() { phase_ = Phase::Prewalk; }
  void BeginEmission() { phase_ = Phase::Emission; }

  template <typename T>
  bool Pre(const T&) {
    return true;
  }

  template <typename T>
  void Post(const T&) {}

  template <typename T>
  bool Pre(const Fortran::parser::Statement<T>& value) {
    const void* identity = fields_.GetIdentity(value);
    if (phase_ == Phase::Prewalk) {
      context_.Reserve(identity);
      return true;
    }

    if (const auto line = getLine(value.source)) {
      flushComments(identity, *line);
    }

    context_.BeginNode(identity, flang_dumper::kStatementTemplateKindId,
                       "Statement");
    fields_.Dump(value.statement, "statement");
    fields_.Dump(value.label, "label");
    fields_.Dump(value.source, "source");
    context_.EndNode();
    writePendingComments();
    return true;
  }

  template <typename T>
  bool Pre(const Fortran::parser::UnlabeledStatement<T>& value) {
    const void* identity = fields_.GetIdentity(value);
    if (phase_ == Phase::Prewalk) {
      context_.Reserve(identity);
      return true;
    }

    context_.BeginNode(identity,
                       flang_dumper::kUnlabeledStatementTemplateKindId,
                       "UnlabeledStatement");
    fields_.Dump(value.statement, "statement");
    fields_.Dump(value.source, "source");
    context_.EndNode();
    return true;
  }

  void flushRemainingComments() {
    while (nextRawComment_ < rawComments_.size()) {
      const RawComment& raw = rawComments_[nextRawComment_++];
      pendingComments_.push_back(PendingComment{raw.text, programId, false});
    }
    writePendingComments();
  }

  void EmitEnumCatalogs() {
#define EMIT_ENUM_CATALOG(Namespace, EnumType)                              \
  emitEnumCatalog(#Namespace "::" #EnumType,                              \
                  Namespace::EnumType##_enumSize,                          \
                  [](std::size_t index) {                                   \
                    return Namespace::EnumToString(                         \
                        static_cast<Namespace::EnumType>(index));           \
                  });
#include "generated_binary_enum_catalogs.inc"
#undef EMIT_ENUM_CATALOG
  }

  template <typename T>
  const void* getId(const T& value) {
    return fields_.GetIdentity(value);
  }

  template <typename T>
  void dump(const T& value, const char* key) {
    fields_.Dump(value, key);
  }

  std::string controlEditDesc_toString(
      Fortran::format::ControlEditDesc::Kind kind) const {
    using Kind = Fortran::format::ControlEditDesc::Kind;
    switch (kind) {
    case Kind::T: return "T";
    case Kind::TL: return "TL";
    case Kind::TR: return "TR";
    case Kind::X: return "X";
    case Kind::Slash: return "Slash";
    case Kind::Colon: return "Colon";
    case Kind::SS: return "SS";
    case Kind::SP: return "SP";
    case Kind::S: return "S";
    case Kind::P: return "P";
    case Kind::BN: return "BN";
    case Kind::BZ: return "BZ";
    case Kind::RU: return "RU";
    case Kind::RD: return "RD";
    case Kind::RZ: return "RZ";
    case Kind::RN: return "RN";
    case Kind::RC: return "RC";
    case Kind::RP: return "RP";
    case Kind::DC: return "DC";
    case Kind::DP: return "DP";
    case Kind::Dollar: return "Dollar";
    case Kind::Backslash: return "Backslash";
    }
    return "Unknown";
  }

  template <typename T>
  void dumpDefaultFields(const T& v) {
    if constexpr (UnionTrait<T>) {
      fields_.Dump(v.u);
    } else if constexpr (TupleTrait<T>) {
      fields_.Dump(v.t);
    } else if constexpr (WrapperTrait<T>) {
      fields_.Dump(v.v, NodeName(v.v));
    } else if constexpr (ConstraintTrait<T>) {
      fields_.Dump(v.thing);
    } else {
      std::cerr << "Not implemented for " << NodeName(v) << '\n';
    }
  }

#define DUMP_NODE(CLASS, CONTENTS)                                          \
  bool Pre(const CLASS& v) {                                                \
    const void* identity = fields_.GetIdentity(v);                          \
    if (phase_ == Phase::Prewalk) {                                         \
      context_.Reserve(identity);                                           \
      return true;                                                          \
    }                                                                       \
    const auto* kind =                                                      \
        flang_dumper::find_ast_kind_by_cpp_type(#CLASS);                    \
    if (kind == nullptr) {                                                  \
      throw std::logic_error("missing AST kind for " #CLASS);              \
    }                                                                       \
    context_.BeginNode(identity, kind->id, NodeName(v));                    \
    dumpDefaultFields(v);                                                   \
    CONTENTS;                                                               \
    context_.EndNode();                                                     \
    return true;                                                            \
  }

#define DUMP_NODE_MANUAL(CLASS, CONTENTS)                                   \
  bool Pre(const CLASS& v) {                                                \
    const void* identity = fields_.GetIdentity(v);                          \
    if (phase_ == Phase::Prewalk) {                                         \
      context_.Reserve(identity);                                           \
      return true;                                                          \
    }                                                                       \
    const auto* kind =                                                      \
        flang_dumper::find_ast_kind_by_cpp_type(#CLASS);                    \
    if (kind == nullptr) {                                                  \
      throw std::logic_error("missing AST kind for " #CLASS);              \
    }                                                                       \
    context_.BeginNode(identity, kind->id, NodeName(v));                    \
    CONTENTS;                                                               \
    context_.EndNode();                                                     \
    return true;                                                            \
  }

#define DUMP_ENUM(Namespace, EnumType)                                     \
  DUMP_NODE(Namespace::EnumType, {                                         \
    dump(#Namespace "::" #EnumType, "disambiguation");                    \
    dump(Namespace::EnumToString(v), "value");                             \
  })

#include "generated_visitor_registrations.inc"

#undef DUMP_ENUM
#undef DUMP_NODE_MANUAL
#undef DUMP_NODE

private:
  enum class Phase { Prewalk, Emission };

  struct PendingComment {
    std::string text;
    const void* stmtIdentity;
    bool trailing;
  };

  std::optional<std::size_t> getLine(
      const Fortran::parser::CharBlock& block) const {
    const auto range = allCooked_.GetSourcePositionRange(block);
    return range.has_value()
               ? std::optional<std::size_t>{range->first.line}
               : std::nullopt;
  }

  void flushComments(const void* stmtIdentity, std::size_t stmtLine) {
    while (nextRawComment_ < rawComments_.size()) {
      RawComment& raw = rawComments_[nextRawComment_];
      if (raw.line < stmtLine ||
          (raw.line == stmtLine && raw.sepsBefore == 0)) {
        pendingComments_.push_back(PendingComment{
            raw.text, stmtIdentity, stmtLine == raw.line});
        ++nextRawComment_;
      } else if (raw.line == stmtLine && raw.sepsBefore > 0) {
        --raw.sepsBefore;
        break;
      } else {
        break;
      }
    }
  }

  void writePendingComments() {
    for (PendingComment& comment : pendingComments_) {
      context_.WriteComment(std::move(comment.text), comment.stmtIdentity,
                            comment.trailing);
    }
    pendingComments_.clear();
  }

  template <typename NameProvider>
  void emitEnumCatalog(const char* typeName, std::size_t enumSize,
                       NameProvider&& nameFor) {
    std::vector<flang_dumper::protocol::EnumEntry> entries;
    entries.reserve(enumSize);
    for (std::size_t i = 0; i < enumSize; ++i) {
      flang_dumper::protocol::EnumEntry entry;
      entry.set_name(std::string{nameFor(i)});
      entry.set_number(static_cast<std::int64_t>(i));
      entries.push_back(std::move(entry));
    }
    context_.WriteEnumCatalog(typeName, entries);
  }

  BinaryContext& context_;
  FieldEncoder fields_;
  const Fortran::parser::AllSources& allSources_;
  const Fortran::parser::AllCookedSources& allCooked_;
  std::vector<RawComment> rawComments_;
  std::vector<PendingComment> pendingComments_;
  std::size_t nextRawComment_ = 0;
  const void* programId = nullptr;
  Phase phase_ = Phase::Prewalk;
};

class DumpASTProtobuf final : public Fortran::frontend::PluginParseTreeAction {
  void executeAction() override {
    const Fortran::parser::AllCookedSources& allCooked =
        getParsing().allCooked();
    const Fortran::parser::AllSources& allSources = allCooked.allSources();

    std::vector<RawComment> rawComments;
    if (const auto first = allSources.GetFirstFileProvenance()) {
      if (const auto* sourceFile = allSources.GetSourceFile(first->start())) {
        rawComments = extractComments(*sourceFile);
      }
    }

    auto output = std::make_unique<std::ostream>(std::cout.rdbuf());
    BinaryContext context{std::move(output)};
    BinaryParseTreeVisitor visitor{context, allSources, allCooked,
                                   std::move(rawComments)};

    visitor.BeginPrewalk();
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
    context.Freeze();

    visitor.BeginEmission();
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
    visitor.flushRemainingComments();
    visitor.EmitEnumCatalogs();
    context.Finish();
    std::cout.flush();
  }
};

const Fortran::frontend::FrontendPluginRegistry::Add<DumpASTProtobuf>
    RegisterDumpASTProtobuf("dump-ast-protobuf",
                            "Dump AST records as a binary protobuf stream");

} // namespace
