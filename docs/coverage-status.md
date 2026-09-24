# Flang generator registration coverage

The registration-only gate checks all 864 dumper registrations against the checked-in Flang 22 declaration model. It finds 860 matching declarations and permits the four reviewed aliases listed below. The CLI command is `python generator/check_registered_coverage.py`.

The gate fails for an unreviewed missing registration, a duplicate registration, a handler/declaration kind mismatch, an unused exception, or any exception outside the four-name alias set. It reports declarations without registrations, but those declarations do not fail this registration-only gate.

## Reviewed aliases

- `Fortran::parser::AcImpliedDoControl::Bounds`
- `Fortran::parser::Block`
- `Fortran::parser::DataImpliedDo::Bounds`
- `Fortran::parser::LoopControl::Bounds`

These names are aliases absent from the declaration inventory. They are explicit exceptions and do not count as matched or generated coverage.

## Remaining review work: 200 declarations

The names below are present in the declaration inventory without dumper registrations. They remain review work and are not covered by the registration gate.

### `include/llvm-22/llvm/Frontend/OpenACC/ACC.inc` (46)

- `Fortran::parser::AccClause::Async`
- `Fortran::parser::AccClause::Attach`
- `Fortran::parser::AccClause::Auto`
- `Fortran::parser::AccClause::Bind`
- `Fortran::parser::AccClause::Capture`
- `Fortran::parser::AccClause::Collapse`
- `Fortran::parser::AccClause::Copy`
- `Fortran::parser::AccClause::Copyin`
- `Fortran::parser::AccClause::Copyout`
- `Fortran::parser::AccClause::Create`
- `Fortran::parser::AccClause::Default`
- `Fortran::parser::AccClause::DefaultAsync`
- `Fortran::parser::AccClause::Delete`
- `Fortran::parser::AccClause::Detach`
- `Fortran::parser::AccClause::Device`
- `Fortran::parser::AccClause::DeviceNum`
- `Fortran::parser::AccClause::DeviceResident`
- `Fortran::parser::AccClause::DeviceType`
- `Fortran::parser::AccClause::Deviceptr`
- `Fortran::parser::AccClause::Finalize`
- `Fortran::parser::AccClause::Firstprivate`
- `Fortran::parser::AccClause::Gang`
- `Fortran::parser::AccClause::Host`
- `Fortran::parser::AccClause::If`
- `Fortran::parser::AccClause::IfPresent`
- `Fortran::parser::AccClause::Independent`
- `Fortran::parser::AccClause::Link`
- `Fortran::parser::AccClause::NoCreate`
- `Fortran::parser::AccClause::Nohost`
- `Fortran::parser::AccClause::NumGangs`
- `Fortran::parser::AccClause::NumWorkers`
- `Fortran::parser::AccClause::Present`
- `Fortran::parser::AccClause::Private`
- `Fortran::parser::AccClause::Read`
- `Fortran::parser::AccClause::Reduction`
- `Fortran::parser::AccClause::Self`
- `Fortran::parser::AccClause::Seq`
- `Fortran::parser::AccClause::Shortloop`
- `Fortran::parser::AccClause::Tile`
- `Fortran::parser::AccClause::Unknown`
- `Fortran::parser::AccClause::UseDevice`
- `Fortran::parser::AccClause::Vector`
- `Fortran::parser::AccClause::VectorLength`
- `Fortran::parser::AccClause::Wait`
- `Fortran::parser::AccClause::Worker`
- `Fortran::parser::AccClause::Write`

### `include/llvm-22/llvm/Frontend/OpenMP/OMP.inc` (130)

- `Fortran::parser::OmpClause::Absent`
- `Fortran::parser::OmpClause::AcqRel`
- `Fortran::parser::OmpClause::Acquire`
- `Fortran::parser::OmpClause::AdjustArgs`
- `Fortran::parser::OmpClause::Affinity`
- `Fortran::parser::OmpClause::Align`
- `Fortran::parser::OmpClause::Aligned`
- `Fortran::parser::OmpClause::Allocate`
- `Fortran::parser::OmpClause::Allocator`
- `Fortran::parser::OmpClause::AppendArgs`
- `Fortran::parser::OmpClause::Apply`
- `Fortran::parser::OmpClause::At`
- `Fortran::parser::OmpClause::AtomicDefaultMemOrder`
- `Fortran::parser::OmpClause::Bind`
- `Fortran::parser::OmpClause::CancellationConstructType`
- `Fortran::parser::OmpClause::Capture`
- `Fortran::parser::OmpClause::Collapse`
- `Fortran::parser::OmpClause::Collector`
- `Fortran::parser::OmpClause::Combiner`
- `Fortran::parser::OmpClause::Compare`
- `Fortran::parser::OmpClause::Contains`
- `Fortran::parser::OmpClause::Copyin`
- `Fortran::parser::OmpClause::Copyprivate`
- `Fortran::parser::OmpClause::Counts`
- `Fortran::parser::OmpClause::Default`
- `Fortran::parser::OmpClause::Defaultmap`
- `Fortran::parser::OmpClause::Depend`
- `Fortran::parser::OmpClause::Depobj`
- `Fortran::parser::OmpClause::Destroy`
- `Fortran::parser::OmpClause::Detach`
- `Fortran::parser::OmpClause::Device`
- `Fortran::parser::OmpClause::DeviceSafesync`
- `Fortran::parser::OmpClause::DeviceType`
- `Fortran::parser::OmpClause::DistSchedule`
- `Fortran::parser::OmpClause::Doacross`
- `Fortran::parser::OmpClause::DynGroupprivate`
- `Fortran::parser::OmpClause::DynamicAllocators`
- `Fortran::parser::OmpClause::Enter`
- `Fortran::parser::OmpClause::Exclusive`
- `Fortran::parser::OmpClause::Fail`
- `Fortran::parser::OmpClause::Filter`
- `Fortran::parser::OmpClause::Final`
- `Fortran::parser::OmpClause::Flush`
- `Fortran::parser::OmpClause::From`
- `Fortran::parser::OmpClause::Full`
- `Fortran::parser::OmpClause::Grainsize`
- `Fortran::parser::OmpClause::GraphId`
- `Fortran::parser::OmpClause::GraphReset`
- `Fortran::parser::OmpClause::Groupprivate`
- `Fortran::parser::OmpClause::HasDeviceAddr`
- `Fortran::parser::OmpClause::Hint`
- `Fortran::parser::OmpClause::Holds`
- `Fortran::parser::OmpClause::If`
- `Fortran::parser::OmpClause::InReduction`
- `Fortran::parser::OmpClause::Inbranch`
- `Fortran::parser::OmpClause::Inclusive`
- `Fortran::parser::OmpClause::Indirect`
- `Fortran::parser::OmpClause::Induction`
- `Fortran::parser::OmpClause::Inductor`
- `Fortran::parser::OmpClause::Init`
- `Fortran::parser::OmpClause::InitComplete`
- `Fortran::parser::OmpClause::Initializer`
- `Fortran::parser::OmpClause::Interop`
- `Fortran::parser::OmpClause::IsDevicePtr`
- `Fortran::parser::OmpClause::Lastprivate`
- `Fortran::parser::OmpClause::Linear`
- `Fortran::parser::OmpClause::Link`
- `Fortran::parser::OmpClause::Local`
- `Fortran::parser::OmpClause::Looprange`
- `Fortran::parser::OmpClause::Map`
- `Fortran::parser::OmpClause::Match`
- `Fortran::parser::OmpClause::MemoryOrder`
- `Fortran::parser::OmpClause::Memscope`
- `Fortran::parser::OmpClause::Mergeable`
- `Fortran::parser::OmpClause::Message`
- `Fortran::parser::OmpClause::NoOpenmp`
- `Fortran::parser::OmpClause::NoOpenmpConstructs`
- `Fortran::parser::OmpClause::NoOpenmpRoutines`
- `Fortran::parser::OmpClause::NoParallelism`
- `Fortran::parser::OmpClause::Nocontext`
- `Fortran::parser::OmpClause::Nogroup`
- `Fortran::parser::OmpClause::Nontemporal`
- `Fortran::parser::OmpClause::Notinbranch`
- `Fortran::parser::OmpClause::Novariants`
- `Fortran::parser::OmpClause::NumTasks`
- `Fortran::parser::OmpClause::NumTeams`
- `Fortran::parser::OmpClause::NumThreads`
- `Fortran::parser::OmpClause::OmpxAttribute`
- `Fortran::parser::OmpClause::OmpxBare`
- `Fortran::parser::OmpClause::OmpxDynCgroupMem`
- `Fortran::parser::OmpClause::Order`
- `Fortran::parser::OmpClause::Otherwise`
- `Fortran::parser::OmpClause::Partial`
- `Fortran::parser::OmpClause::Permutation`
- `Fortran::parser::OmpClause::Priority`
- `Fortran::parser::OmpClause::ProcBind`
- `Fortran::parser::OmpClause::Read`
- `Fortran::parser::OmpClause::Relaxed`
- `Fortran::parser::OmpClause::Release`
- `Fortran::parser::OmpClause::Replayable`
- `Fortran::parser::OmpClause::ReverseOffload`
- `Fortran::parser::OmpClause::Safelen`
- `Fortran::parser::OmpClause::Safesync`
- `Fortran::parser::OmpClause::Schedule`
- `Fortran::parser::OmpClause::SelfMaps`
- `Fortran::parser::OmpClause::SeqCst`
- `Fortran::parser::OmpClause::Severity`
- `Fortran::parser::OmpClause::Simd`
- `Fortran::parser::OmpClause::Simdlen`
- `Fortran::parser::OmpClause::Sizes`
- `Fortran::parser::OmpClause::TaskReduction`
- `Fortran::parser::OmpClause::ThreadLimit`
- `Fortran::parser::OmpClause::Threadprivate`
- `Fortran::parser::OmpClause::Threads`
- `Fortran::parser::OmpClause::Threadset`
- `Fortran::parser::OmpClause::To`
- `Fortran::parser::OmpClause::Transparent`
- `Fortran::parser::OmpClause::UnifiedAddress`
- `Fortran::parser::OmpClause::UnifiedSharedMemory`
- `Fortran::parser::OmpClause::Uniform`
- `Fortran::parser::OmpClause::Unknown`
- `Fortran::parser::OmpClause::Untied`
- `Fortran::parser::OmpClause::Update`
- `Fortran::parser::OmpClause::Use`
- `Fortran::parser::OmpClause::UseDeviceAddr`
- `Fortran::parser::OmpClause::UseDevicePtr`
- `Fortran::parser::OmpClause::UsesAllocators`
- `Fortran::parser::OmpClause::Weak`
- `Fortran::parser::OmpClause::When`
- `Fortran::parser::OmpClause::Write`

### `lib/llvm-22/include/flang/Parser/format-specification.h` (1)

- `Fortran::format::ControlEditDesc::Kind`

### `lib/llvm-22/include/flang/Parser/parse-tree.h` (17)

- `Fortran::parser::Constant`
- `Fortran::parser::DefaultChar`
- `Fortran::parser::Expr::IntrinsicBinary`
- `Fortran::parser::Expr::IntrinsicUnary`
- `Fortran::parser::Integer`
- `Fortran::parser::Logical`
- `Fortran::parser::LoopBounds`
- `Fortran::parser::OmpDirectiveNameModifier`
- `Fortran::parser::OmpFallbackModifier::Value`
- `Fortran::parser::OmpInitClause::Modifier`
- `Fortran::parser::OpenMPAtomicConstruct::Analysis`
- `Fortran::parser::OpenMPAtomicConstruct::Analysis::Op`
- `Fortran::parser::OpenMPExecDirective`
- `Fortran::parser::PartRef`
- `Fortran::parser::Scalar`
- `Fortran::parser::Statement`
- `Fortran::parser::UnlabeledStatement`

### `lib/llvm-22/include/flang/Support/Fortran.h` (6)

- `Fortran::common::IgnoreTKR`
- `Fortran::common::Intent`
- `Fortran::common::IoSpecKind`
- `Fortran::common::LogicalOperator`
- `Fortran::common::NumericOperator`
- `Fortran::common::RelationalOperator`
