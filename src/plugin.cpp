#include <sstream>
#include <type_traits>

#include <llvm/Support/raw_ostream.h>

#include "flang/Common/Fortran.h"
#include "flang/Frontend/FrontendActions.h"
#include "flang/Frontend/FrontendPluginRegistry.h"
#include "flang/Parser/dump-parse-tree.h"
#include "flang/Parser/parse-tree.h"

#include "plugin.h"

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
  } else if constexpr (is_specialization<T, Fortran::parser::Scalar>::value) {
    return "Scalar";
  } else if constexpr (is_specialization<T, Fortran::parser::Constant>::value) {
    return "Constant";
  } else if constexpr (is_specialization<T, Fortran::parser::Integer>::value) {
    return "Integer";
  } else if constexpr (is_specialization<T, Fortran::parser::Logical>::value) {
    return "Logical";
  } else if constexpr (is_specialization<T,
                                         Fortran::parser::DefaultChar>::value) {
    return "DefaultChar";
  } else if constexpr (std::is_same_v<T, Fortran::parser::CharBlock>) {
    return "CharBlock";
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
    llvm::outs() << "\"" << getId(value) << "\"";
  }
};

template <typename T> void dump(const T &v, const char *property_name) {
  DUMP_PROPERTY(property_name, getId(v));
}

void dump(const char *v, const char *property_name) {
  DUMP_PROPERTY(property_name, v);
}

void dump(std::string_view v, const char *property_name) {
  DUMP_PROPERTY(property_name, v);
}

void dump(const std::uint64_t v, const char *property_name) {
  DUMP_PROPERTY(property_name, v)
}

template <> void dump(const std::string &v, const char *property_name) {
  dump(v.c_str(), property_name);
}

template <>
void dump(const Fortran::parser::CharBlock &v, const char *property_name) {
  dump(v.ToString(), property_name);
}

template <> void dump(const std::nullopt_t &v, const char *property_name) {
  if (!strcmp(property_name, "null")) {
    return;
  }

  dump("null", property_name);
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
  llvm::outs() << ",\n\"" << property_name << "\": ";
  std::visit(variant_visitor{}, v);
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
  using ThisClass = ParseTreeVisitor;
  bool firstNodeDump = true;

  template <typename A> bool Pre(const A &) { return true; }
  template <typename A> void Post(const A &) { return; }

  template <typename T> static void dump_enum() {
    // llvm::outs() << T::name() << ": " << T::value() << '\n';
  }

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

  template <typename T> bool Pre(const Fortran::parser::Statement<T> &v) {
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

  // NODE_NAME(bool, "bool")
  // NODE_NAME(int, "int")
  // DUMP_NODE(std::string, {})
  // DUMP_NODE(std::int64_t, {})
  // DUMP_NODE(std::uint64_t, {})
  DUMP_ENUM(Fortran::common, CUDADataAttr)
  DUMP_ENUM(Fortran::common, CUDASubprogramAttrs)
  DUMP_ENUM(Fortran::common, OpenACCDeviceType)
  DUMP_NODE(Fortran::format::ControlEditDesc, {})
  DUMP_NODE(Fortran::format::ControlEditDesc::Kind, {})
  DUMP_NODE(Fortran::format::DerivedTypeDataEditDesc, {})
  DUMP_NODE(Fortran::format::FormatItem, {})
  DUMP_NODE(Fortran::format::FormatSpecification, {})
  DUMP_NODE(Fortran::format::IntrinsicTypeDataEditDesc, {})
  DUMP_NODE(Fortran::format::IntrinsicTypeDataEditDesc::Kind, {})
  DUMP_NODE(Fortran::parser::Abstract, {})
  DUMP_NODE(Fortran::parser::AccAtomicCapture, {})
  DUMP_NODE(Fortran::parser::AccAtomicCapture::Stmt1, {})
  DUMP_NODE(Fortran::parser::AccAtomicCapture::Stmt2, {})
  DUMP_NODE(Fortran::parser::AccAtomicRead, {})
  DUMP_NODE(Fortran::parser::AccAtomicUpdate, {})
  DUMP_NODE(Fortran::parser::AccAtomicWrite, {})
  DUMP_NODE(Fortran::parser::AccBeginBlockDirective, {})
  DUMP_NODE(Fortran::parser::AccBeginCombinedDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccBeginLoopDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccBlockDirective, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccClause, {})
  DUMP_NODE(Fortran::parser::AccBindClause, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccDefaultClause, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccClauseList, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccCombinedDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccDataModifier, { dump(v.source, "source"); })
  DUMP_ENUM(Fortran::parser::AccDataModifier, Modifier)
  DUMP_NODE(Fortran::parser::AccDeclarativeDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccEndAtomic, {})
  DUMP_NODE(Fortran::parser::AccEndBlockDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccEndCombinedDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccCollapseArg, {})
  DUMP_NODE(Fortran::parser::AccGangArg, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccGangArg::Num, {})
  DUMP_NODE(Fortran::parser::AccGangArg::Dim, {})
  DUMP_NODE(Fortran::parser::AccGangArg::Static, {})
  DUMP_NODE(Fortran::parser::AccGangArgList, {})
  DUMP_NODE(Fortran::parser::AccObject, {})
  DUMP_NODE(Fortran::parser::AccObjectList, {})
  DUMP_NODE(Fortran::parser::AccObjectListWithModifier, {})
  DUMP_NODE(Fortran::parser::AccObjectListWithReduction, {})
  DUMP_NODE(Fortran::parser::AccSizeExpr, {})
  DUMP_NODE(Fortran::parser::AccSizeExprList, {})
  DUMP_NODE(Fortran::parser::AccSelfClause, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccStandaloneDirective,
            { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccDeviceTypeExpr, { dump(v.source, "source"); })
  DUMP_NODE(Fortran::parser::AccDeviceTypeExprList, {})
  DUMP_NODE(Fortran::parser::AccTileExpr, {})
  DUMP_NODE(Fortran::parser::AccTileExprList, {})
  DUMP_NODE(Fortran::parser::AccLoopDirective, {})
  DUMP_NODE(Fortran::parser::AccEndLoop, {})
  DUMP_NODE(Fortran::parser::AccWaitArgument, {})
  DUMP_NODE(Fortran::parser::AcImpliedDo, {})
  DUMP_NODE(Fortran::parser::AcImpliedDoControl, {})
  DUMP_NODE(Fortran::parser::AcValue, {})
  DUMP_NODE(Fortran::parser::AccessStmt, {})
  DUMP_NODE(Fortran::parser::AccessId, {})
  DUMP_NODE(Fortran::parser::AccessSpec, {})
  DUMP_ENUM(Fortran::parser::AccessSpec, Kind)
  DUMP_NODE(Fortran::parser::AcSpec, {})
  DUMP_NODE(Fortran::parser::ActionStmt, {})
  DUMP_NODE(Fortran::parser::ActualArg, {})
  DUMP_NODE(Fortran::parser::ActualArg::PercentRef, {})
  DUMP_NODE(Fortran::parser::ActualArg::PercentVal, {})
  DUMP_NODE(Fortran::parser::ActualArgSpec, {})
  DUMP_NODE(Fortran::parser::AcValue::Triplet, {})
  DUMP_NODE(Fortran::parser::AllocOpt, {})
  DUMP_NODE(Fortran::parser::AllocOpt::Mold, {})
  DUMP_NODE(Fortran::parser::AllocOpt::Source, {})
  DUMP_NODE(Fortran::parser::AllocOpt::Stream, {})
  DUMP_NODE(Fortran::parser::AllocOpt::Pinned, {})
  DUMP_NODE(Fortran::parser::Allocatable, {})
  DUMP_NODE(Fortran::parser::AllocatableStmt, {})
  DUMP_NODE(Fortran::parser::AllocateCoarraySpec, {})
  DUMP_NODE(Fortran::parser::AllocateObject, {})
  DUMP_NODE(Fortran::parser::AllocateShapeSpec, {})
  DUMP_NODE(Fortran::parser::AllocateStmt, {})
  DUMP_NODE(Fortran::parser::Allocation, {})
  DUMP_NODE(Fortran::parser::AltReturnSpec, {})
  DUMP_NODE(Fortran::parser::ArithmeticIfStmt, {})
  DUMP_NODE(Fortran::parser::ArrayConstructor, {})
  DUMP_NODE(Fortran::parser::ArrayElement, {})
  DUMP_NODE(Fortran::parser::ArraySpec, {})
  DUMP_NODE(Fortran::parser::AssignStmt, {})
  DUMP_NODE(Fortran::parser::AssignedGotoStmt, {})
  DUMP_NODE(Fortran::parser::AssignmentStmt, {})
  DUMP_NODE(Fortran::parser::AssociateConstruct, {})
  DUMP_NODE(Fortran::parser::AssociateStmt, {})
  DUMP_NODE(Fortran::parser::Association, {})
  DUMP_NODE(Fortran::parser::AssumedImpliedSpec, {})
  DUMP_NODE(Fortran::parser::AssumedRankSpec, {})
  DUMP_NODE(Fortran::parser::AssumedShapeSpec, {})
  DUMP_NODE(Fortran::parser::AssumedSizeSpec, {})
  DUMP_NODE(Fortran::parser::Asynchronous, {})
  DUMP_NODE(Fortran::parser::AsynchronousStmt, {})
  DUMP_NODE(Fortran::parser::AttrSpec, {})
  DUMP_NODE(Fortran::parser::BOZLiteralConstant, {})
  DUMP_NODE(Fortran::parser::BackspaceStmt, {})
  DUMP_NODE(Fortran::parser::BasedPointer, {})
  DUMP_NODE(Fortran::parser::BasedPointerStmt, {})
  DUMP_NODE(Fortran::parser::BindAttr, {})
  DUMP_NODE(Fortran::parser::BindAttr::Deferred, {})
  DUMP_NODE(Fortran::parser::BindAttr::Non_Overridable, {})
  DUMP_NODE(Fortran::parser::BindEntity, {})
  DUMP_ENUM(Fortran::parser::BindEntity, Kind)
  DUMP_NODE(Fortran::parser::BindStmt, {})
  DUMP_NODE(Fortran::parser::Block, {})
  DUMP_NODE(Fortran::parser::BlockConstruct, {})
  DUMP_NODE(Fortran::parser::BlockData, {})
  DUMP_NODE(Fortran::parser::BlockDataStmt, {})
  DUMP_NODE(Fortran::parser::BlockSpecificationPart, {})
  DUMP_NODE(Fortran::parser::BlockStmt, {})
  DUMP_NODE(Fortran::parser::BoundsRemapping, {})
  DUMP_NODE(Fortran::parser::BoundsSpec, {})
  DUMP_NODE(Fortran::parser::Call, {})
  DUMP_NODE(Fortran::parser::CallStmt, {})
  DUMP_NODE(Fortran::parser::CallStmt::Chevrons, {})
  DUMP_NODE(Fortran::parser::CallStmt::StarOrExpr, {})
  DUMP_NODE(Fortran::parser::CaseConstruct, {})
  DUMP_NODE(Fortran::parser::CaseConstruct::Case, {})
  DUMP_NODE(Fortran::parser::CaseSelector, {})
  DUMP_NODE(Fortran::parser::CaseStmt, {})
  DUMP_NODE(Fortran::parser::CaseValueRange, {})
  DUMP_NODE(Fortran::parser::CaseValueRange::Range, {})
  DUMP_NODE(Fortran::parser::ChangeTeamConstruct, {})
  DUMP_NODE(Fortran::parser::ChangeTeamStmt, {})
  DUMP_NODE(Fortran::parser::CharLength, {})
  DUMP_NODE(Fortran::parser::CharLiteralConstant, {})
  DUMP_NODE(Fortran::parser::CharLiteralConstantSubstring, {})
  DUMP_NODE(Fortran::parser::CharSelector, {})
  DUMP_NODE(Fortran::parser::CharSelector::LengthAndKind, {})
  DUMP_NODE(Fortran::parser::CloseStmt, {})
  DUMP_NODE(Fortran::parser::CloseStmt::CloseSpec, {})
  DUMP_NODE(Fortran::parser::CoarrayAssociation, {})
  DUMP_NODE(Fortran::parser::CoarraySpec, {})
  DUMP_NODE(Fortran::parser::CodimensionDecl, {})
  DUMP_NODE(Fortran::parser::CodimensionStmt, {})
  DUMP_NODE(Fortran::parser::CoindexedNamedObject, {})
  DUMP_NODE(Fortran::parser::CommonBlockObject, {})
  DUMP_NODE(Fortran::parser::CommonStmt, {})
  DUMP_NODE(Fortran::parser::CommonStmt::Block, {})
  DUMP_NODE(Fortran::parser::CompilerDirective, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::AssumeAligned, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::IgnoreTKR, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::LoopCount, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::NameValue, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::Unrecognized, {})
  DUMP_NODE(Fortran::parser::CompilerDirective::VectorAlways, {})
  DUMP_NODE(Fortran::parser::ComplexLiteralConstant, {})
  DUMP_NODE(Fortran::parser::ComplexPart, {})
  DUMP_NODE(Fortran::parser::ComponentArraySpec, {})
  DUMP_NODE(Fortran::parser::ComponentAttrSpec, {})
  DUMP_NODE(Fortran::parser::ComponentDataSource, {})
  DUMP_NODE(Fortran::parser::ComponentDecl, {})
  DUMP_NODE(Fortran::parser::FillDecl, {})
  DUMP_NODE(Fortran::parser::ComponentOrFill, {})
  DUMP_NODE(Fortran::parser::ComponentDefStmt, {})
  DUMP_NODE(Fortran::parser::ComponentSpec, {})
  DUMP_NODE(Fortran::parser::ComputedGotoStmt, {})
  DUMP_NODE(Fortran::parser::ConcurrentControl, {})
  DUMP_NODE(Fortran::parser::ConcurrentHeader, {})
  DUMP_NODE(Fortran::parser::ConnectSpec, {})
  DUMP_NODE(Fortran::parser::ConnectSpec::CharExpr, {})
  DUMP_ENUM(Fortran::parser::ConnectSpec::CharExpr, Kind)
  DUMP_NODE(Fortran::parser::ConnectSpec::Newunit, {})
  DUMP_NODE(Fortran::parser::ConnectSpec::Recl, {})
  DUMP_NODE(Fortran::parser::ContainsStmt, {})
  DUMP_NODE(Fortran::parser::Contiguous, {})
  DUMP_NODE(Fortran::parser::ContiguousStmt, {})
  DUMP_NODE(Fortran::parser::ContinueStmt, {})
  DUMP_NODE(Fortran::parser::CriticalConstruct, {})
  DUMP_NODE(Fortran::parser::CriticalStmt, {})
  DUMP_NODE(Fortran::parser::CUDAAttributesStmt, {})
  DUMP_NODE(Fortran::parser::CUFKernelDoConstruct, {})
  DUMP_NODE(Fortran::parser::CUFKernelDoConstruct::StarOrExpr, {})
  DUMP_NODE(Fortran::parser::CUFKernelDoConstruct::Directive, {})
  DUMP_NODE(Fortran::parser::CUFKernelDoConstruct::LaunchConfiguration, {})
  DUMP_NODE(Fortran::parser::CUFReduction, {})
  DUMP_NODE(Fortran::parser::CycleStmt, {})
  DUMP_NODE(Fortran::parser::DataComponentDefStmt, {})
  DUMP_NODE(Fortran::parser::DataIDoObject, {})
  DUMP_NODE(Fortran::parser::DataImpliedDo, {})
  DUMP_NODE(Fortran::parser::DataRef, {})
  DUMP_NODE(Fortran::parser::DataStmt, {})
  DUMP_NODE(Fortran::parser::DataStmtConstant, {})
  DUMP_NODE(Fortran::parser::DataStmtObject, {})
  DUMP_NODE(Fortran::parser::DataStmtRepeat, {})
  DUMP_NODE(Fortran::parser::DataStmtSet, {})
  DUMP_NODE(Fortran::parser::DataStmtValue, {})
  DUMP_NODE(Fortran::parser::DeallocateStmt, {})
  DUMP_NODE(Fortran::parser::DeclarationConstruct, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec::Class, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec::ClassStar, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec::Record, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec::Type, {})
  DUMP_NODE(Fortran::parser::DeclarationTypeSpec::TypeStar, {})
  DUMP_NODE(Fortran::parser::Default, {})
  DUMP_NODE(Fortran::parser::DeferredCoshapeSpecList, {})
  DUMP_NODE(Fortran::parser::DeferredShapeSpecList, {})
  DUMP_NODE(Fortran::parser::DefinedOpName, {})
  DUMP_NODE(Fortran::parser::DefinedOperator, {})
  DUMP_ENUM(Fortran::parser::DefinedOperator, IntrinsicOperator)
  DUMP_NODE(Fortran::parser::DerivedTypeDef, {})
  DUMP_NODE(Fortran::parser::DerivedTypeSpec, {})
  DUMP_NODE(Fortran::parser::DerivedTypeStmt, {})
  DUMP_NODE(Fortran::parser::Designator, {})
  DUMP_NODE(Fortran::parser::DimensionStmt, {})
  DUMP_NODE(Fortran::parser::DimensionStmt::Declaration, {})
  DUMP_NODE(Fortran::parser::DoConstruct, {})
  DUMP_NODE(Fortran::parser::DummyArg, {})
  DUMP_NODE(Fortran::parser::ElseIfStmt, {})
  DUMP_NODE(Fortran::parser::ElseStmt, {})
  DUMP_NODE(Fortran::parser::ElsewhereStmt, {})
  DUMP_NODE(Fortran::parser::EndAssociateStmt, {})
  DUMP_NODE(Fortran::parser::EndBlockDataStmt, {})
  DUMP_NODE(Fortran::parser::EndBlockStmt, {})
  DUMP_NODE(Fortran::parser::EndChangeTeamStmt, {})
  DUMP_NODE(Fortran::parser::EndCriticalStmt, {})
  DUMP_NODE(Fortran::parser::EndDoStmt, {})
  DUMP_NODE(Fortran::parser::EndEnumStmt, {})
  DUMP_NODE(Fortran::parser::EndForallStmt, {})
  DUMP_NODE(Fortran::parser::EndFunctionStmt, {})
  DUMP_NODE(Fortran::parser::EndIfStmt, {})
  DUMP_NODE(Fortran::parser::EndInterfaceStmt, {})
  DUMP_NODE(Fortran::parser::EndLabel, {})
  DUMP_NODE(Fortran::parser::EndModuleStmt, {})
  DUMP_NODE(Fortran::parser::EndMpSubprogramStmt, {})
  DUMP_NODE(Fortran::parser::EndProgramStmt, {})
  DUMP_NODE(Fortran::parser::EndSelectStmt, {})
  DUMP_NODE(Fortran::parser::EndSubmoduleStmt, {})
  DUMP_NODE(Fortran::parser::EndSubroutineStmt, {})
  DUMP_NODE(Fortran::parser::EndTypeStmt, {})
  DUMP_NODE(Fortran::parser::EndWhereStmt, {})
  DUMP_NODE(Fortran::parser::EndfileStmt, {})
  DUMP_NODE(Fortran::parser::EntityDecl, {})
  DUMP_NODE(Fortran::parser::EntryStmt, {})
  DUMP_NODE(Fortran::parser::EnumDef, {})
  DUMP_NODE(Fortran::parser::EnumDefStmt, {})
  DUMP_NODE(Fortran::parser::Enumerator, {})
  DUMP_NODE(Fortran::parser::EnumeratorDefStmt, {})
  DUMP_NODE(Fortran::parser::EorLabel, {})
  DUMP_NODE(Fortran::parser::EquivalenceObject, {})
  DUMP_NODE(Fortran::parser::EquivalenceStmt, {})
  DUMP_NODE(Fortran::parser::ErrLabel, {})
  DUMP_NODE(Fortran::parser::ErrorRecovery, {})
  DUMP_NODE(Fortran::parser::EventPostStmt, {})
  DUMP_NODE(Fortran::parser::EventWaitSpec, {})
  DUMP_NODE(Fortran::parser::EventWaitStmt, {})
  DUMP_NODE(Fortran::parser::ExecutableConstruct, {})
  DUMP_NODE(Fortran::parser::ExecutionPart, {})
  DUMP_NODE(Fortran::parser::ExecutionPartConstruct, {})
  DUMP_NODE(Fortran::parser::ExitStmt, {})
  DUMP_NODE(Fortran::parser::ExplicitCoshapeSpec, {})
  DUMP_NODE(Fortran::parser::ExplicitShapeSpec, {})
  DUMP_NODE(Fortran::parser::Expr, {})
  DUMP_NODE(Fortran::parser::Expr::Parentheses, {})
  DUMP_NODE(Fortran::parser::Expr::UnaryPlus, {})
  DUMP_NODE(Fortran::parser::Expr::Negate, {})
  DUMP_NODE(Fortran::parser::Expr::NOT, {})
  DUMP_NODE(Fortran::parser::Expr::PercentLoc, {})
  DUMP_NODE(Fortran::parser::Expr::DefinedUnary, {})
  DUMP_NODE(Fortran::parser::Expr::Power, {})
  DUMP_NODE(Fortran::parser::Expr::Multiply, {})
  DUMP_NODE(Fortran::parser::Expr::Divide, {})
  DUMP_NODE(Fortran::parser::Expr::Add, {})
  DUMP_NODE(Fortran::parser::Expr::Subtract, {})
  DUMP_NODE(Fortran::parser::Expr::Concat, {})
  DUMP_NODE(Fortran::parser::Expr::LT, {})
  DUMP_NODE(Fortran::parser::Expr::LE, {})
  DUMP_NODE(Fortran::parser::Expr::EQ, {})
  DUMP_NODE(Fortran::parser::Expr::NE, {})
  DUMP_NODE(Fortran::parser::Expr::GE, {})
  DUMP_NODE(Fortran::parser::Expr::GT, {})
  DUMP_NODE(Fortran::parser::Expr::AND, {})
  DUMP_NODE(Fortran::parser::Expr::OR, {})
  DUMP_NODE(Fortran::parser::Expr::EQV, {})
  DUMP_NODE(Fortran::parser::Expr::NEQV, {})
  DUMP_NODE(Fortran::parser::Expr::DefinedBinary, {})
  DUMP_NODE(Fortran::parser::Expr::ComplexConstructor, {})
  DUMP_NODE(Fortran::parser::External, {})
  DUMP_NODE(Fortran::parser::ExternalStmt, {})
  DUMP_NODE(Fortran::parser::FailImageStmt, {})
  DUMP_NODE(Fortran::parser::FileUnitNumber, {})
  DUMP_NODE(Fortran::parser::FinalProcedureStmt, {})
  DUMP_NODE(Fortran::parser::FlushStmt, {})
  DUMP_NODE(Fortran::parser::ForallAssignmentStmt, {})
  DUMP_NODE(Fortran::parser::ForallBodyConstruct, {})
  DUMP_NODE(Fortran::parser::ForallConstruct, {})
  DUMP_NODE(Fortran::parser::ForallConstructStmt, {})
  DUMP_NODE(Fortran::parser::ForallStmt, {})
  DUMP_NODE(Fortran::parser::FormTeamStmt, {})
  DUMP_NODE(Fortran::parser::FormTeamStmt::FormTeamSpec, {})
  DUMP_NODE(Fortran::parser::Format, {})
  DUMP_NODE(Fortran::parser::FormatStmt, {})
  DUMP_NODE(Fortran::parser::FunctionReference, {})
  DUMP_NODE(Fortran::parser::FunctionStmt, {})
  DUMP_NODE(Fortran::parser::FunctionSubprogram, {})
  DUMP_NODE(Fortran::parser::GenericSpec, {})
  DUMP_NODE(Fortran::parser::GenericSpec::Assignment, {})
  DUMP_NODE(Fortran::parser::GenericSpec::ReadFormatted, {})
  DUMP_NODE(Fortran::parser::GenericSpec::ReadUnformatted, {})
  DUMP_NODE(Fortran::parser::GenericSpec::WriteFormatted, {})
  DUMP_NODE(Fortran::parser::GenericSpec::WriteUnformatted, {})
  DUMP_NODE(Fortran::parser::GenericStmt, {})
  DUMP_NODE(Fortran::parser::GotoStmt, {})
  DUMP_NODE(Fortran::parser::HollerithLiteralConstant, {})
  DUMP_NODE(Fortran::parser::IdExpr, {})
  DUMP_NODE(Fortran::parser::IdVariable, {})
  DUMP_NODE(Fortran::parser::IfConstruct, {})
  DUMP_NODE(Fortran::parser::IfConstruct::ElseBlock, {})
  DUMP_NODE(Fortran::parser::IfConstruct::ElseIfBlock, {})
  DUMP_NODE(Fortran::parser::IfStmt, {})
  DUMP_NODE(Fortran::parser::IfThenStmt, {})
  DUMP_NODE(Fortran::parser::TeamValue, {})
  DUMP_NODE(Fortran::parser::ImageSelector, {})
  DUMP_NODE(Fortran::parser::ImageSelectorSpec, {})
  DUMP_NODE(Fortran::parser::ImageSelectorSpec::Stat, {})
  DUMP_NODE(Fortran::parser::ImageSelectorSpec::Team_Number, {})
  DUMP_NODE(Fortran::parser::ImplicitPart, {})
  DUMP_NODE(Fortran::parser::ImplicitPartStmt, {})
  DUMP_NODE(Fortran::parser::ImplicitSpec, {})
  DUMP_NODE(Fortran::parser::ImplicitStmt, {})
  DUMP_ENUM(Fortran::parser::ImplicitStmt, ImplicitNoneNameSpec)
  DUMP_NODE(Fortran::parser::ImpliedShapeSpec, {})
  DUMP_NODE(Fortran::parser::ImportStmt, {})
  DUMP_NODE(Fortran::parser::Initialization, {})
  DUMP_NODE(Fortran::parser::InputImpliedDo, {})
  DUMP_NODE(Fortran::parser::InputItem, {})
  DUMP_NODE(Fortran::parser::InquireSpec, {})
  DUMP_NODE(Fortran::parser::InquireSpec::CharVar, {})
  DUMP_ENUM(Fortran::parser::InquireSpec::CharVar, Kind)
  DUMP_NODE(Fortran::parser::InquireSpec::IntVar, {})
  DUMP_ENUM(Fortran::parser::InquireSpec::IntVar, Kind)
  DUMP_NODE(Fortran::parser::InquireSpec::LogVar, {})
  DUMP_ENUM(Fortran::parser::InquireSpec::LogVar, Kind)
  DUMP_NODE(Fortran::parser::InquireStmt, {})
  DUMP_NODE(Fortran::parser::InquireStmt::Iolength, {})
  DUMP_NODE(Fortran::parser::IntegerTypeSpec, {})
  DUMP_NODE(Fortran::parser::IntentSpec, {})
  DUMP_ENUM(Fortran::parser::IntentSpec, Intent)
  DUMP_NODE(Fortran::parser::IntentStmt, {})
  DUMP_NODE(Fortran::parser::InterfaceBlock, {})
  DUMP_NODE(Fortran::parser::InterfaceBody, {})
  DUMP_NODE(Fortran::parser::InterfaceBody::Function, {})
  DUMP_NODE(Fortran::parser::InterfaceBody::Subroutine, {})
  DUMP_NODE(Fortran::parser::InterfaceSpecification, {})
  DUMP_NODE(Fortran::parser::InterfaceStmt, {})
  DUMP_NODE(Fortran::parser::InternalSubprogram, {})
  DUMP_NODE(Fortran::parser::InternalSubprogramPart, {})
  DUMP_NODE(Fortran::parser::Intrinsic, {})
  DUMP_NODE(Fortran::parser::IntrinsicStmt, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::Character, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::Complex, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::DoubleComplex, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::DoublePrecision, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::Logical, {})
  DUMP_NODE(Fortran::parser::IntrinsicTypeSpec::Real, {})
  DUMP_NODE(Fortran::parser::IoControlSpec, {})
  DUMP_NODE(Fortran::parser::IoControlSpec::Asynchronous, {})
  DUMP_NODE(Fortran::parser::IoControlSpec::CharExpr, {})
  DUMP_ENUM(Fortran::parser::IoControlSpec::CharExpr, Kind)
  DUMP_NODE(Fortran::parser::IoControlSpec::Pos, {})
  DUMP_NODE(Fortran::parser::IoControlSpec::Rec, {})
  DUMP_NODE(Fortran::parser::IoControlSpec::Size, {})
  DUMP_NODE(Fortran::parser::IoUnit, {})
  DUMP_NODE(Fortran::parser::Keyword, {})
  DUMP_NODE(Fortran::parser::KindParam, {})
  DUMP_NODE(Fortran::parser::KindSelector, {})
  DUMP_NODE(Fortran::parser::KindSelector::StarSize, {})
  DUMP_NODE(Fortran::parser::LabelDoStmt, {})
  DUMP_NODE(Fortran::parser::LanguageBindingSpec, {})
  DUMP_NODE(Fortran::parser::LengthSelector, {})
  DUMP_NODE(Fortran::parser::LetterSpec, {})
  DUMP_NODE(Fortran::parser::LiteralConstant, {})
  DUMP_NODE(Fortran::parser::IntLiteralConstant, {})
  DUMP_NODE(Fortran::parser::ReductionOperator, {})
  DUMP_ENUM(Fortran::parser::ReductionOperator, Operator)
  DUMP_NODE(Fortran::parser::LocalitySpec, {})
  DUMP_NODE(Fortran::parser::LocalitySpec::DefaultNone, {})
  DUMP_NODE(Fortran::parser::LocalitySpec::Local, {})
  DUMP_NODE(Fortran::parser::LocalitySpec::LocalInit, {})
  DUMP_NODE(Fortran::parser::LocalitySpec::Reduce, {})
  DUMP_NODE(Fortran::parser::LocalitySpec::Shared, {})
  DUMP_NODE(Fortran::parser::LockStmt, {})
  DUMP_NODE(Fortran::parser::LockStmt::LockStat, {})
  DUMP_NODE(Fortran::parser::LogicalLiteralConstant, {})
  // NODE_NAME(LoopControl::Bounds, "LoopBounds")
  // NODE_NAME(AcImpliedDoControl::Bounds, "LoopBounds")
  // NODE_NAME(DataImpliedDo::Bounds, "LoopBounds")
  DUMP_NODE(Fortran::parser::LoopControl, {})
  DUMP_NODE(Fortran::parser::LoopControl::Concurrent, {})
  DUMP_NODE(Fortran::parser::MainProgram, {})
  DUMP_NODE(Fortran::parser::Map, {})
  DUMP_NODE(Fortran::parser::Map::EndMapStmt, {})
  DUMP_NODE(Fortran::parser::Map::MapStmt, {})
  DUMP_NODE(Fortran::parser::MaskedElsewhereStmt, {})
  DUMP_NODE(Fortran::parser::Module, {})
  DUMP_NODE(Fortran::parser::ModuleStmt, {})
  DUMP_NODE(Fortran::parser::ModuleSubprogram, {})
  DUMP_NODE(Fortran::parser::ModuleSubprogramPart, {})
  DUMP_NODE(Fortran::parser::MpSubprogramStmt, {})
  DUMP_NODE(Fortran::parser::MsgVariable, {})
  DUMP_NODE(Fortran::parser::Name, {})
  DUMP_NODE(Fortran::parser::NamedConstant, {})
  DUMP_NODE(Fortran::parser::NamedConstantDef, {})
  DUMP_NODE(Fortran::parser::NamelistStmt, {})
  DUMP_NODE(Fortran::parser::NamelistStmt::Group, {})
  DUMP_NODE(Fortran::parser::NonLabelDoStmt, {})
  DUMP_NODE(Fortran::parser::NoPass, {})
  DUMP_NODE(Fortran::parser::NotifyWaitStmt, {})
  DUMP_NODE(Fortran::parser::NullifyStmt, {})
  DUMP_NODE(Fortran::parser::NullInit, {})
  DUMP_NODE(Fortran::parser::ObjectDecl, {})
  DUMP_NODE(Fortran::parser::OldParameterStmt, {})
  DUMP_NODE(Fortran::parser::OmpTraitPropertyName, {})
  DUMP_NODE(Fortran::parser::OmpTraitScore, {})
  DUMP_NODE(Fortran::parser::OmpTraitPropertyExtension, {})
  DUMP_NODE(Fortran::parser::OmpTraitPropertyExtension::ExtensionValue, {})
  DUMP_NODE(Fortran::parser::OmpTraitProperty, {})
  DUMP_NODE(Fortran::parser::OmpTraitSelectorName, {})
  DUMP_ENUM(Fortran::parser::OmpTraitSelectorName, Value)
  DUMP_NODE(Fortran::parser::OmpTraitSelector, {})
  DUMP_NODE(Fortran::parser::OmpTraitSelector::Properties, {})
  DUMP_NODE(Fortran::parser::OmpTraitSetSelectorName, {})
  DUMP_ENUM(Fortran::parser::OmpTraitSetSelectorName, Value)
  DUMP_NODE(Fortran::parser::OmpTraitSetSelector, {})
  DUMP_NODE(Fortran::parser::OmpContextSelectorSpecification, {})
  DUMP_NODE(Fortran::parser::OmpMapper, {})
  DUMP_NODE(Fortran::parser::OmpMapType, {})
  DUMP_ENUM(Fortran::parser::OmpMapType, Value)
  DUMP_NODE(Fortran::parser::OmpMapTypeModifier, {})
  DUMP_ENUM(Fortran::parser::OmpMapTypeModifier, Value)
  DUMP_NODE(Fortran::parser::OmpIteratorSpecifier, {})
  DUMP_NODE(Fortran::parser::OmpIterator, {})
  DUMP_NODE(Fortran::parser::OmpAffinityClause, {})
  DUMP_NODE(Fortran::parser::OmpAffinityClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpAlignment, {})
  DUMP_NODE(Fortran::parser::OmpAlignClause, {})
  DUMP_NODE(Fortran::parser::OmpAlignedClause, {})
  DUMP_NODE(Fortran::parser::OmpAlignedClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpAtClause, {})
  DUMP_ENUM(Fortran::parser::OmpAtClause, ActionTime)
  DUMP_ENUM(Fortran::parser::OmpSeverityClause, Severity)
  DUMP_NODE(Fortran::parser::OmpAtomic, {})
  DUMP_NODE(Fortran::parser::OmpAtomicCapture, {})
  DUMP_NODE(Fortran::parser::OmpAtomicCapture::Stmt1, {})
  DUMP_NODE(Fortran::parser::OmpAtomicCapture::Stmt2, {})
  DUMP_NODE(Fortran::parser::OmpAtomicCompare, {})
  DUMP_NODE(Fortran::parser::OmpAtomicCompareIfStmt, {})
  DUMP_NODE(Fortran::parser::OmpAtomicRead, {})
  DUMP_NODE(Fortran::parser::OmpAtomicUpdate, {})
  DUMP_NODE(Fortran::parser::OmpAtomicWrite, {})
  DUMP_NODE(Fortran::parser::OmpBeginBlockDirective, {})
  DUMP_NODE(Fortran::parser::OmpBeginLoopDirective, {})
  DUMP_NODE(Fortran::parser::OmpBeginSectionsDirective, {})
  DUMP_NODE(Fortran::parser::OmpBlockDirective, {})
  DUMP_NODE(Fortran::parser::OmpCancelType, {})
  DUMP_ENUM(Fortran::parser::OmpCancelType, Type)
  DUMP_NODE(Fortran::parser::OmpClause, {})
  DUMP_NODE(Fortran::parser::OmpClauseList, {})
  DUMP_NODE(Fortran::parser::OmpCriticalDirective, {})
  DUMP_NODE(Fortran::parser::OmpErrorDirective, {})
  DUMP_NODE(Fortran::parser::OmpNothingDirective, {})
  DUMP_NODE(Fortran::parser::OmpDeclareTargetSpecifier, {})
  DUMP_NODE(Fortran::parser::OmpDeclareTargetWithClause, {})
  DUMP_NODE(Fortran::parser::OmpDeclareTargetWithList, {})
  DUMP_NODE(Fortran::parser::OmpDeclareMapperSpecifier, {})
  DUMP_NODE(Fortran::parser::OmpDefaultClause, {})
  DUMP_ENUM(Fortran::parser::OmpDefaultClause, DataSharingAttribute)
  DUMP_NODE(Fortran::parser::OmpVariableCategory, {})
  DUMP_ENUM(Fortran::parser::OmpVariableCategory, Value)
  DUMP_NODE(Fortran::parser::OmpDefaultmapClause, {})
  DUMP_ENUM(Fortran::parser::OmpDefaultmapClause, ImplicitBehavior)
  DUMP_NODE(Fortran::parser::OmpDefaultmapClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpDependenceType, {})
  DUMP_ENUM(Fortran::parser::OmpDependenceType, Value)
  DUMP_NODE(Fortran::parser::OmpTaskDependenceType, {})
  DUMP_ENUM(Fortran::parser::OmpTaskDependenceType, Value)
  DUMP_NODE(Fortran::parser::OmpIterationOffset, {})
  DUMP_NODE(Fortran::parser::OmpIteration, {})
  DUMP_NODE(Fortran::parser::OmpIterationVector, {})
  DUMP_NODE(Fortran::parser::OmpDoacross, {})
  DUMP_NODE(Fortran::parser::OmpDoacross::Sink, {})
  DUMP_NODE(Fortran::parser::OmpDoacross::Source, {})
  DUMP_NODE(Fortran::parser::OmpDependClause, {})
  DUMP_NODE(Fortran::parser::OmpDependClause::TaskDep, {})
  DUMP_NODE(Fortran::parser::OmpDependClause::TaskDep::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpDetachClause, {})
  DUMP_NODE(Fortran::parser::OmpDoacrossClause, {})
  DUMP_NODE(Fortran::parser::OmpDestroyClause, {})
  DUMP_NODE(Fortran::parser::OmpEndAllocators, {})
  DUMP_NODE(Fortran::parser::OmpEndAtomic, {})
  DUMP_NODE(Fortran::parser::OmpEndBlockDirective, {})
  DUMP_NODE(Fortran::parser::OmpEndCriticalDirective, {})
  DUMP_NODE(Fortran::parser::OmpEndLoopDirective, {})
  DUMP_NODE(Fortran::parser::OmpEndSectionsDirective, {})
  DUMP_NODE(Fortran::parser::OmpFailClause, {})
  DUMP_NODE(Fortran::parser::OmpFromClause, {})
  DUMP_NODE(Fortran::parser::OmpFromClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpExpectation, {})
  DUMP_ENUM(Fortran::parser::OmpExpectation, Value)
  DUMP_NODE(Fortran::parser::OmpDirectiveNameModifier, {})
  DUMP_NODE(Fortran::parser::OmpIfClause, {})
  DUMP_NODE(Fortran::parser::OmpIfClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpLastprivateClause, {})
  DUMP_NODE(Fortran::parser::OmpLastprivateClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpLastprivateModifier, {})
  DUMP_ENUM(Fortran::parser::OmpLastprivateModifier, Value)
  DUMP_NODE(Fortran::parser::OmpLinearClause, {})
  DUMP_NODE(Fortran::parser::OmpLinearClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpLinearModifier, {})
  DUMP_ENUM(Fortran::parser::OmpLinearModifier, Value)
  DUMP_NODE(Fortran::parser::OmpStepComplexModifier, {})
  DUMP_NODE(Fortran::parser::OmpStepSimpleModifier, {})
  DUMP_NODE(Fortran::parser::OmpLoopDirective, {})
  DUMP_NODE(Fortran::parser::OmpMapClause, {})
  DUMP_NODE(Fortran::parser::OmpMessageClause, {})
  DUMP_NODE(Fortran::parser::OmpMapClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpObject, {})
  DUMP_NODE(Fortran::parser::OmpObjectList, {})
  DUMP_NODE(Fortran::parser::OmpOrderClause, {})
  DUMP_NODE(Fortran::parser::OmpOrderClause::Modifier, {})
  DUMP_ENUM(Fortran::parser::OmpOrderClause, Ordering)
  DUMP_NODE(Fortran::parser::OmpOrderModifier, {})
  DUMP_ENUM(Fortran::parser::OmpOrderModifier, Value)
  DUMP_NODE(Fortran::parser::OmpGrainsizeClause, {})
  DUMP_NODE(Fortran::parser::OmpGrainsizeClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpPrescriptiveness, {})
  DUMP_ENUM(Fortran::parser::OmpPrescriptiveness, Value)
  DUMP_NODE(Fortran::parser::OmpNumTasksClause, {})
  DUMP_NODE(Fortran::parser::OmpNumTasksClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpBindClause, {})
  DUMP_ENUM(Fortran::parser::OmpBindClause, Binding)
  DUMP_NODE(Fortran::parser::OmpProcBindClause, {})
  DUMP_ENUM(Fortran::parser::OmpProcBindClause, AffinityPolicy)
  DUMP_NODE(Fortran::parser::OmpReductionModifier, {})
  DUMP_ENUM(Fortran::parser::OmpReductionModifier, Value)
  DUMP_NODE(Fortran::parser::OmpReductionClause, {})
  DUMP_NODE(Fortran::parser::OmpReductionClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpInReductionClause, {})
  DUMP_NODE(Fortran::parser::OmpInReductionClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpReductionCombiner, {})
  DUMP_NODE(Fortran::parser::OmpTaskReductionClause, {})
  DUMP_NODE(Fortran::parser::OmpTaskReductionClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpReductionCombiner::FunctionCombiner, {})
  DUMP_NODE(Fortran::parser::OmpReductionInitializerClause, {})
  DUMP_NODE(Fortran::parser::OmpReductionIdentifier, {})
  DUMP_NODE(Fortran::parser::OmpAllocateClause, {})
  DUMP_NODE(Fortran::parser::OmpAllocateClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpAlignModifier, {})
  DUMP_NODE(Fortran::parser::OmpAllocatorComplexModifier, {})
  DUMP_NODE(Fortran::parser::OmpAllocatorSimpleModifier, {})
  DUMP_NODE(Fortran::parser::OmpScheduleClause, {})
  DUMP_NODE(Fortran::parser::OmpScheduleClause::Modifier, {})
  DUMP_ENUM(Fortran::parser::OmpScheduleClause, Kind)
  DUMP_NODE(Fortran::parser::OmpSeverityClause, {})
  DUMP_NODE(Fortran::parser::OmpDeviceClause, {})
  DUMP_NODE(Fortran::parser::OmpDeviceClause::Modifier, {})
  DUMP_NODE(Fortran::parser::OmpDeviceModifier, {})
  DUMP_ENUM(Fortran::parser::OmpDeviceModifier, Value)
  DUMP_NODE(Fortran::parser::OmpDeviceTypeClause, {})
  DUMP_ENUM(Fortran::parser::OmpDeviceTypeClause, DeviceTypeDescription)
  DUMP_NODE(Fortran::parser::OmpUpdateClause, {})
  DUMP_NODE(Fortran::parser::OmpChunkModifier, {})
  DUMP_ENUM(Fortran::parser::OmpChunkModifier, Value)
  DUMP_NODE(Fortran::parser::OmpOrderingModifier, {})
  DUMP_ENUM(Fortran::parser::OmpOrderingModifier, Value)
  DUMP_NODE(Fortran::parser::OmpSectionBlocks, {})
  DUMP_NODE(Fortran::parser::OmpSectionsDirective, {})
  DUMP_NODE(Fortran::parser::OmpSimpleStandaloneDirective, {})
  DUMP_NODE(Fortran::parser::OmpToClause, {})
  DUMP_NODE(Fortran::parser::OmpToClause::Modifier, {})
  DUMP_NODE(Fortran::parser::Only, {})
  DUMP_NODE(Fortran::parser::OpenACCAtomicConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCBlockConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCCacheConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCCombinedConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCDeclarativeConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCEndConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCLoopConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCRoutineConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCStandaloneDeclarativeConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCStandaloneConstruct, {})
  DUMP_NODE(Fortran::parser::OpenACCWaitConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPAtomicConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPBlockConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPCancelConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPCancelConstruct::If, {})
  DUMP_NODE(Fortran::parser::OpenMPCancellationPointConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPCriticalConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclarativeAllocate, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclarativeConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclareReductionConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclareSimdConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclareTargetConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDeclareMapperConstruct, {})
  DUMP_NODE(Fortran::parser::OmpMemoryOrderClause, {})
  DUMP_NODE(Fortran::parser::OmpAtomicClause, {})
  DUMP_NODE(Fortran::parser::OmpAtomicClauseList, {})
  DUMP_NODE(Fortran::parser::OmpAtomicDefaultMemOrderClause, {})
  DUMP_ENUM(Fortran::common, OmpAtomicDefaultMemOrderType)
  DUMP_NODE(Fortran::parser::OpenMPDepobjConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPUtilityConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPDispatchConstruct, {})
  DUMP_NODE(Fortran::parser::OmpDispatchDirective, {})
  DUMP_NODE(Fortran::parser::OmpEndDispatchDirective, {})
  DUMP_NODE(Fortran::parser::OpenMPFlushConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPLoopConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPExecutableAllocate, {})
  DUMP_NODE(Fortran::parser::OpenMPAllocatorsConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPRequiresConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPSimpleStandaloneConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPStandaloneConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPSectionConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPSectionsConstruct, {})
  DUMP_NODE(Fortran::parser::OpenMPThreadprivate, {})
  DUMP_NODE(Fortran::parser::OpenStmt, {})
  DUMP_NODE(Fortran::parser::Optional, {})
  DUMP_NODE(Fortran::parser::OptionalStmt, {})
  DUMP_NODE(Fortran::parser::OtherSpecificationStmt, {})
  DUMP_NODE(Fortran::parser::OutputImpliedDo, {})
  DUMP_NODE(Fortran::parser::OutputItem, {})
  DUMP_NODE(Fortran::parser::Parameter, {})
  DUMP_NODE(Fortran::parser::ParameterStmt, {})
  DUMP_NODE(Fortran::parser::ParentIdentifier, {})
  DUMP_NODE(Fortran::parser::Pass, {})
  DUMP_NODE(Fortran::parser::PauseStmt, {})
  DUMP_NODE(Fortran::parser::Pointer, {})
  DUMP_NODE(Fortran::parser::PointerAssignmentStmt, {})
  DUMP_NODE(Fortran::parser::PointerAssignmentStmt::Bounds, {})
  DUMP_NODE(Fortran::parser::PointerDecl, {})
  DUMP_NODE(Fortran::parser::PointerObject, {})
  DUMP_NODE(Fortran::parser::PointerStmt, {})
  DUMP_NODE(Fortran::parser::PositionOrFlushSpec, {})
  DUMP_NODE(Fortran::parser::PrefixSpec, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Elemental, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Impure, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Module, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Non_Recursive, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Pure, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Recursive, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Attributes, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Launch_Bounds, {})
  DUMP_NODE(Fortran::parser::PrefixSpec::Cluster_Dims, {})
  DUMP_NODE(Fortran::parser::PrintStmt, {})
  DUMP_NODE(Fortran::parser::PrivateStmt, {})
  DUMP_NODE(Fortran::parser::PrivateOrSequence, {})
  DUMP_NODE(Fortran::parser::ProcAttrSpec, {})
  DUMP_NODE(Fortran::parser::ProcComponentAttrSpec, {})
  DUMP_NODE(Fortran::parser::ProcComponentDefStmt, {})
  DUMP_NODE(Fortran::parser::ProcComponentRef, {})
  DUMP_NODE(Fortran::parser::ProcDecl, {})
  DUMP_NODE(Fortran::parser::ProcInterface, {})
  DUMP_NODE(Fortran::parser::ProcPointerInit, {})
  DUMP_NODE(Fortran::parser::ProcedureDeclarationStmt, {})
  DUMP_NODE(Fortran::parser::ProcedureDesignator, {})
  DUMP_NODE(Fortran::parser::ProcedureStmt, {})
  DUMP_ENUM(Fortran::parser::ProcedureStmt, Kind)
  DUMP_NODE(Fortran::parser::Program, {})
  DUMP_NODE(Fortran::parser::ProgramStmt, {})
  DUMP_NODE(Fortran::parser::ProgramUnit, {})
  DUMP_NODE(Fortran::parser::Protected, {})
  DUMP_NODE(Fortran::parser::ProtectedStmt, {})
  DUMP_NODE(Fortran::parser::ReadStmt, {})
  DUMP_NODE(Fortran::parser::RealLiteralConstant, {})
  DUMP_NODE(Fortran::parser::RealLiteralConstant::Real, {})
  DUMP_NODE(Fortran::parser::Rename, {})
  DUMP_NODE(Fortran::parser::Rename::Names, {})
  DUMP_NODE(Fortran::parser::Rename::Operators, {})
  DUMP_NODE(Fortran::parser::ReturnStmt, {})
  DUMP_NODE(Fortran::parser::RewindStmt, {})
  DUMP_NODE(Fortran::parser::Save, {})
  DUMP_NODE(Fortran::parser::SaveStmt, {})
  DUMP_NODE(Fortran::parser::SavedEntity, {})
  DUMP_ENUM(Fortran::parser::SavedEntity, Kind)
  DUMP_NODE(Fortran::parser::SectionSubscript, {})
  DUMP_NODE(Fortran::parser::SelectCaseStmt, {})
  DUMP_NODE(Fortran::parser::SelectRankCaseStmt, {})
  DUMP_NODE(Fortran::parser::SelectRankCaseStmt::Rank, {})
  DUMP_NODE(Fortran::parser::SelectRankConstruct, {})
  DUMP_NODE(Fortran::parser::SelectRankConstruct::RankCase, {})
  DUMP_NODE(Fortran::parser::SelectRankStmt, {})
  DUMP_NODE(Fortran::parser::SelectTypeConstruct, {})
  DUMP_NODE(Fortran::parser::SelectTypeConstruct::TypeCase, {})
  DUMP_NODE(Fortran::parser::SelectTypeStmt, {})
  DUMP_NODE(Fortran::parser::Selector, {})
  DUMP_NODE(Fortran::parser::SeparateModuleSubprogram, {})
  DUMP_NODE(Fortran::parser::SequenceStmt, {})
  DUMP_NODE(Fortran::parser::Sign, {})
  DUMP_NODE(Fortran::parser::SignedComplexLiteralConstant, {})
  DUMP_NODE(Fortran::parser::SignedIntLiteralConstant, {})
  DUMP_NODE(Fortran::parser::SignedRealLiteralConstant, {})
  DUMP_NODE(Fortran::parser::SpecificationConstruct, {})
  DUMP_NODE(Fortran::parser::SpecificationExpr, {})
  DUMP_NODE(Fortran::parser::SpecificationPart, {})
  DUMP_NODE(Fortran::parser::Star, {})
  DUMP_NODE(Fortran::parser::StatOrErrmsg, {})
  DUMP_NODE(Fortran::parser::StatVariable, {})
  DUMP_NODE(Fortran::parser::StatusExpr, {})
  DUMP_NODE(Fortran::parser::StmtFunctionStmt, {})
  DUMP_NODE(Fortran::parser::StopCode, {})
  DUMP_NODE(Fortran::parser::StopStmt, {})
  DUMP_ENUM(Fortran::parser::StopStmt, Kind)
  DUMP_NODE(Fortran::parser::StructureComponent, {})
  DUMP_NODE(Fortran::parser::StructureConstructor, {})
  DUMP_NODE(Fortran::parser::StructureDef, {})
  DUMP_NODE(Fortran::parser::StructureDef::EndStructureStmt, {})
  DUMP_NODE(Fortran::parser::StructureField, {})
  DUMP_NODE(Fortran::parser::StructureStmt, {})
  DUMP_NODE(Fortran::parser::Submodule, {})
  DUMP_NODE(Fortran::parser::SubmoduleStmt, {})
  DUMP_NODE(Fortran::parser::SubroutineStmt, {})
  DUMP_NODE(Fortran::parser::SubroutineSubprogram, {})
  DUMP_NODE(Fortran::parser::SubscriptTriplet, {})
  DUMP_NODE(Fortran::parser::Substring, {})
  DUMP_NODE(Fortran::parser::SubstringInquiry, {})
  DUMP_NODE(Fortran::parser::SubstringRange, {})
  DUMP_NODE(Fortran::parser::Suffix, {})
  DUMP_NODE(Fortran::parser::SyncAllStmt, {})
  DUMP_NODE(Fortran::parser::SyncImagesStmt, {})
  DUMP_NODE(Fortran::parser::SyncImagesStmt::ImageSet, {})
  DUMP_NODE(Fortran::parser::SyncMemoryStmt, {})
  DUMP_NODE(Fortran::parser::SyncTeamStmt, {})
  DUMP_NODE(Fortran::parser::Target, {})
  DUMP_NODE(Fortran::parser::TargetStmt, {})
  DUMP_NODE(Fortran::parser::TypeAttrSpec, {})
  DUMP_NODE(Fortran::parser::TypeAttrSpec::BindC, {})
  DUMP_NODE(Fortran::parser::TypeAttrSpec::Extends, {})
  DUMP_NODE(Fortran::parser::TypeBoundGenericStmt, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcBinding, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcDecl, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcedurePart, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcedureStmt, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcedureStmt::WithInterface, {})
  DUMP_NODE(Fortran::parser::TypeBoundProcedureStmt::WithoutInterface, {})
  DUMP_NODE(Fortran::parser::TypeDeclarationStmt, {})
  DUMP_NODE(Fortran::parser::TypeGuardStmt, {})
  DUMP_NODE(Fortran::parser::TypeGuardStmt::Guard, {})
  DUMP_NODE(Fortran::parser::TypeParamDecl, {})
  DUMP_NODE(Fortran::parser::TypeParamDefStmt, {})
  DUMP_NODE(Fortran::common::TypeParamAttr, {})
  DUMP_NODE(Fortran::parser::TypeParamSpec, {})
  DUMP_NODE(Fortran::parser::TypeParamValue, {})
  DUMP_NODE(Fortran::parser::TypeParamValue::Deferred, {})
  DUMP_NODE(Fortran::parser::TypeSpec, {})
  DUMP_NODE(Fortran::parser::Union, {})
  DUMP_NODE(Fortran::parser::Union::EndUnionStmt, {})
  DUMP_NODE(Fortran::parser::Union::UnionStmt, {})
  DUMP_NODE(Fortran::parser::UnlockStmt, {})
  DUMP_NODE(Fortran::parser::UnsignedLiteralConstant, {})
  DUMP_NODE(Fortran::parser::UnsignedTypeSpec, {})
  DUMP_NODE(Fortran::parser::UseStmt, {})
  DUMP_ENUM(Fortran::parser::UseStmt, ModuleNature)
  DUMP_NODE(Fortran::parser::Value, {})
  DUMP_NODE(Fortran::parser::ValueStmt, {})
  DUMP_NODE(Fortran::parser::Variable, {})
  DUMP_NODE(Fortran::parser::VectorTypeSpec, {})
  DUMP_NODE(Fortran::parser::VectorTypeSpec::PairVectorTypeSpec, {})
  DUMP_NODE(Fortran::parser::VectorTypeSpec::QuadVectorTypeSpec, {})
  DUMP_NODE(Fortran::parser::IntrinsicVectorTypeSpec, {})
  DUMP_NODE(Fortran::parser::VectorElementType, {})
  DUMP_NODE(Fortran::parser::Verbatim, {})
  DUMP_NODE(Fortran::parser::Volatile, {})
  DUMP_NODE(Fortran::parser::VolatileStmt, {})
  DUMP_NODE(Fortran::parser::WaitSpec, {})
  DUMP_NODE(Fortran::parser::WaitStmt, {})
  DUMP_NODE(Fortran::parser::WhereBodyConstruct, {})
  DUMP_NODE(Fortran::parser::WhereConstruct, {})
  DUMP_NODE(Fortran::parser::WhereConstruct::Elsewhere, {})
  DUMP_NODE(Fortran::parser::WhereConstruct::MaskedElsewhere, {})
  DUMP_NODE(Fortran::parser::WhereConstructStmt, {})
  DUMP_NODE(Fortran::parser::WhereStmt, {})
  DUMP_NODE(Fortran::parser::WriteStmt, {})
};

class DumpAST : public Fortran::frontend::PluginParseTreeAction {

  void executeAction() override {
    llvm::outs() << "{\"nodes\": [\n";
    ParseTreeVisitor visitor;
    Fortran::parser::Walk(getParsing().parseTree(), visitor);
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
