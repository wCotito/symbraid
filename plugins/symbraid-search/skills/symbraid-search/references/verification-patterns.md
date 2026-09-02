# Verification patterns

Use these only after semantic discovery has identified candidate languages and symbols.

## Exact checks

```powershell
rg -n --fixed-strings "SymbolName" path\to\candidate
rg -n "refresh[_-]?token|renew.*session" src tests
```

Bound searches to candidate files or directories and cap output before broadening.

## ast-grep examples

JavaScript and TypeScript calls:

```powershell
ast-grep run --lang ts --pattern '$FUNC($$$ARGS)' src
ast-grep run --lang ts --pattern 'renewSessionCredentials($$$ARGS)' src
```

Python calls and definitions:

```powershell
ast-grep run --lang python --pattern '$FUNC($$$ARGS)' src
ast-grep run --lang python --pattern 'def $NAME($$$ARGS): $$$BODY' src
```

Rust functions and calls:

```powershell
ast-grep run --lang rust --pattern 'fn $NAME($$$ARGS) { $$$BODY }' src
ast-grep run --lang rust --pattern '$FUNC($$$ARGS)' src
```

Use a language-native symbol or reference tool when it is available and more precise. AST matches remain candidates until the relevant source and callers are read.
