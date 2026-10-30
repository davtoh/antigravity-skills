# Multi-Language Decomposition Playbooks & Fallback Bailout Guide

Load this reference **only** when decomposing non-Python source files (`.js`, `.ts`, `.tsx`, `.jsx`, `.css`, `.scss`, `.dart`, `.go`, `.rs`, `.cs`) or when `code_health_audit.py` reports `Parser: fallback`.

---

## Table of Contents
1. [Pre-Flight Check: Source vs. Compiled/Theme Assets](#1-pre-flight-check-source-vs-compiledtheme-assets)
2. [JavaScript, TypeScript, JSX & TSX (`.js`, `.ts`, `.jsx`, `.tsx`)](#2-javascript-typescript-jsx--tsx-js-ts-jsx-tsx)
3. [Stylesheets: CSS & SCSS (`.css`, `.scss`, `.less`)](#3-stylesheets-css--scss-css-scss-less)
4. [Dart & Flutter (`.dart`)](#4-dart--flutter-dart)
5. [Compiled Languages: Go, Rust & C# (`.go`, `.rs`, `.cs`)](#5-compiled-languages-go-rust--c-go-rs-cs)
6. [Unknown Languages & The "Best Working Version" Bailout Protocol](#6-unknown-languages--the-best-working-version-bailout-protocol)

---

## 1. Pre-Flight Check: Source vs. Compiled/Theme Assets

Before splitting any frontend or non-Python file flagged by `code_health_audit.py`:
1. **Check for Upstream Source Files**:
   - If `static/css/main.css` is flagged alongside `static/scss/theme/*.scss`, `main.css` is likely a **compiled output** of the SCSS pipeline.
   - **Rule**: Never manually split a compiled output file if its SCSS/TS source exists—refactor the upstream `.scss` or `.ts` partials instead and re-run the build, or ask the user which is the canonical source of truth.
2. **Check for Purchased/Downloaded HTML/CSS Templates**:
   - Legacy projects often include a 3,000-line theme stylesheet (`main.css`, `style.css`). Only decompose it if the user wants to modularize the theme; otherwise prioritize first-party backend/frontend application logic first.

---

## 2. JavaScript, TypeScript, JSX & TSX (`.js`, `.ts`, `.jsx`, `.tsx`)

### Zero-Breaking-Import Facade (ES Module Barrel Pattern)
Convert `src/api.ts` (1,200 lines) into a directory `src/api/index.ts` (or keep `src/api.ts` as a re-export barrel):

```typescript
// src/api.ts — Backward-Compatible Barrel Facade
export * from "./api/types";
export * from "./api/authClient";
export * from "./api/streamClient";
export { ApiClient as default } from "./api/coreClient";
```

### React / JSX / TSX Component Monoliths
When a single `.tsx`/`.jsx` file exceeds 350–500 lines:
1. **Extract Custom Hooks (`use<Feature>.ts`)**: Move `useState`, `useEffect`, data fetching, and event handlers out of the component body into a dedicated hook file.
2. **Extract Pure Sub-Components**: Move self-contained JSX sections (modals, table rows, filter bars, cards) into sibling components (`components/<Feature>Header.tsx`).
3. **Extract Pure Helpers & Constants**: Move data formatters, validation schemas, and column definitions into `<feature>.utils.ts` or `<feature>.types.ts`.

---

## 3. Stylesheets: CSS & SCSS (`.css`, `.scss`, `.less`)

### Safe Decomposition Strategy (Zero Cascade Regressions)
CSS depends on source order and specificity. Splitting a 3,500-line `main.css` blindly can break cascade overrides if rules are reordered. Follow **ITCSS (Inverted Triangle CSS)** ordering:

1. `tokens.css` / `_variables.scss`: `:root` custom properties (`--color-*`, `--space-*`), font-face declarations, and keyframes (`@keyframes`).
2. `base.css` / `_reset.scss`: Element resets (`body`, `a`, `h1`-`h6`) and typography defaults.
3. `layout.css` / `_layout.scss`: Page shell, grid containers, header, navigation (`.nav-menu*`), and footer (`.footer-area*`).
4. `components/<name>.css`: Cohesive component clusters identified by `code_health_audit.py --show-methods` (e.g., `buttons.css` for `.genric-btn*`, `tables.css` for `.progress-table*`, `cards.css`).

### Preserving Single `<link>` Compatibility
- **In SCSS**: Keep `main.scss` as `@use` / `@import` manifest in exact cascade order and compile to `main.css`.
- **In Plain CSS**: Keep `main.css` as an `@import url("./components/...");` manifest (or update the bundler/template) while keeping the exact rule sequence intact.
- **Strict Rule**: Never introduce `!important` to fix specificity shifts during a split—preserve original selector specificity and cascade order.

---

## 4. Dart & Flutter (`.dart`)

### Zero-Breaking-Import Facade (`export` or `part` / `part of`)
Dart offers two native, zero-regression ways to split a monolithic `.dart` file:

1. **Barrel Re-Export (Preferred for Clean Boundaries)**:
   Keep `lib/feature/dashboard.dart` and re-export extracted files:
   ```dart
   // lib/feature/dashboard.dart
   export 'src/dashboard_screen.dart';
   export 'src/dashboard_controller.dart';
   export 'src/dashboard_models.dart';
   ```
2. **`part` / `part of` Directive (When Sharing File-Private `_` Symbols)**:
   If a God class or state class relies heavily on library-private `_fields` and `_methods`, use `part 'dashboard_widgets.dart';` in the main file and `part of 'dashboard.dart';` in the extracted slice so private access works without making internals public.
3. **Widget Method Rule**:
   Never keep helper methods like `Widget _buildHeader(BuildContext context)` exceeding 30–40 lines inside a `State` class—extract them into standalone `StatelessWidget` classes with `const` constructors for better Flutter rebuild performance.

---

## 5. Compiled Languages: Go, Rust & C# (`.go`, `.rs`, `.cs`)

### Go (`.go`) — Same-Package File Splitting (Zero Import Changes!)
- In Go, all `.go` files in the same directory belong to the same `package` and share both exported (`PascalCase`) and unexported (`camelCase`) symbols automatically.
- **Action**: Split a 1,500-line `service.go` directly into sibling files in the same folder (`service.go`, `service_auth.go`, `service_metrics.go`, `service_types.go`) with the same `package <name>` header. **Zero external imports or call sites change.**

### Rust (`.rs`) — Submodules with `pub use` Re-Exports
- Convert `src/engine.rs` into `src/engine/mod.rs` (or keep `src/engine.rs` with submodules in `src/engine/`):
  ```rust
  // src/engine.rs
  mod parser;
  mod worker;
  pub use self::parser::*;
  pub use self::worker::*;
  ```
- Separate data structs from large `impl` blocks—Rust allows multiple `impl MyStruct` blocks across different submodules within the same crate!

### C# (`.cs`) — Namespace Co-Location & `partial class`
- **Multiple Classes in One File**: Move each class/interface/enum into its own `<ClassName>.cs` file under the exact same `namespace`. Existing `using` directives across the solution continue working with zero edits.
- **Single Giant God Class**: If one class has 30 methods and cannot be decomposed into collaborator services yet, mark the class `public partial class OrderService` and split cohesive method groups into `OrderService.Validation.cs` and `OrderService.Billing.cs`, then extract focused domain services incrementally.

---

## 6. Unknown Languages & The "Best Working Version" Bailout Protocol

When `code_health_audit.py` reports `Parser: fallback` (or when dealing with an unfamiliar language, macro-heavy DSL, or legacy framework):

1. **Never Act Blindly**:
   - Do **not** guess how module imports, visibility, or linker symbols work in an unfamiliar language.
   - Check if a language server (LSP), compiler check, or `ctags` (`ctags -x <file>`) is available in the environment to inspect symbol boundaries safely.
   - If the module system or test runner is unclear, **pause and use `ask_question`, `/plan`, or `/grill-me`** to align with the user before editing.

2. **The "Leave at Best Working Version" Bailout Rule**:
   - Not every file should be forcibly split. If a fallback approach or complex refactoring slice:
     - Fails unit tests or build checks after 2 attempts, **OR**
     - Requires ugly workarounds, global state hacks, or circular references that make the code **worse or less maintainable** than the previous version:
   - **Mandatory Action**:
     1. **Revert the unstable slice immediately** (`git checkout -- <files>` or remove partial files) back to the **last verified best working version**.
     2. Explain clearly to the user why splitting that specific construct degrades quality or hits tooling/language constraints.
     3. Recommend either leaving that file at its best working version or trying an alternative strategy—and **do not force further edits unless the user explicitly instructs you to continue**.


---

## 7. Deterministic Safe Callbacks & Rollback Recipes (When Something Goes Wrong)

Whenever a refactoring slice encounters errors, circular imports, or failing tests, execute the appropriate safe callback immediately:

### Callback 1: Unstable Git Edits (Fastest & Safest)
```bash
# Revert modified files to restore the last verified green milestone
git checkout -- <modified_monolith_file>

# Remove any newly created uncommitted submodules/partial files
git clean -fd <path_to_new_submodule_dir>
```

### Callback 2: Non-Git / Local Workspace Backup
Before modifying any multi-thousand line file without Git version control:
```bash
# Snapshot the working file before slice extraction
cp <target_file> <target_file>.working_bak

# If slice extraction fails verification twice, restore immediately:
mv <target_file>.working_bak <target_file>
```

### Callback 3: Circular Import Deadlock Safe Callback
If `ImportError: cannot import name ... from partially initialized module` occurs:
1. Do not use local inside-function imports (`def func(): import X`) as permanent band-aids.
2. Immediately extract the shared types, models, or constants to a **Level 0 Leaf Module** (`types.py`, `constants.ts`, `models.go`).
3. Re-run `code_health_audit.py` to confirm the DAG is strictly unidirectional before proceeding.
