# Shelffiles

Shelffiles is a portable environment configuration system that uses Nix to manage packages and configuration files. It's designed to be easy to set up and use across different systems.

## Getting Started

### Prerequisites

- [Nix package manager](https://nixos.org/download.html) with flakes enabled

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/shelffiles.git
   cd shelffiles
   ```

2. Build the environment:
   ```bash
   nix build
   ```

3. Enter the environment:
   ```bash
   # Use the shell-specific entrypoint
   ./entrypoint/zsh    # For zsh
   ./entrypoint/fish   # For fish
   ./entrypoint/bash   # For bash
   ```

## Portable runtime export (Linux)

After the ordinary `nix build` succeeds, you can export that existing `result`
closure into this checkout by choosing its required runtime prefix:

```bash
SHELFFILES_PORTABLE_PREFIX=/tmp/foo42 ./utils/create_portable.sh
```

The exporter saves a valid process-environment prefix in
`config/shelffiles.conf` after the export succeeds, so later runs need no
variable:

```bash
./utils/create_portable.sh
```

The saved assignment is marked as managed by `utils/create_portable.sh`.
Unrelated settings, comments, and manually maintained prefix assignments are
preserved. Repeated successful exports remove old managed copies and append one
canonical managed assignment after the preserved content, so the saved value is
effective on the next config-only run. A prefix read from the configuration file
is not written back unnecessarily.
If saving the configuration fails after the artifact commits, the command
prints a warning but leaves the successful artifact active and exits
successfully. Fix the configuration path and rerun with the intended process
environment prefix to retry persistence.

`SHELFFILES_PORTABLE_PREFIX` has no default and must match exactly
`/tmp/[A-Za-z0-9]{5}`. The complete path is therefore 10 ASCII bytes, the same
length as `/nix/store`. A definition in the process environment wins over the
configuration file, including an explicitly empty environment value; an empty
or otherwise invalid winning value fails rather than falling back. When the
process environment does not define the variable, the exporter uses an
assignment from `config/shelffiles.conf`, whether manually maintained or
previously saved by the exporter.

The exporter requires Linux, an existing `result` that resolves to a
`/nix/store/<hash>-...` directory, and `nix-store --query --requisites`
(available either on `PATH` or in `result/bin`). It does not run another build,
download packages, write to `/nix/store`, or change the ordinary `result`. It
copies the required runtime closure into `portable/nix/store` and creates a
relative `portable/result` symlink.

Enter the exported environment with the portable wrappers:

```bash
./portable/entrypoint/bash
./portable/entrypoint/fish
./portable/entrypoint/zsh
```

The ordinary `entrypoint/*` commands remain unchanged by default and continue
to use the ordinary `result`. Both modes share this checkout's `config`,
`cache`, `share`, and `state` directories. The portable wrappers source the
ordinary environment setup first, then place `portable/result/bin` before the
ordinary result in `PATH`. Once the portable artifact has been validated, the
portable wrappers launch it directly and never fall back to the ordinary
`launch_in_bwrap.sh` path when `result` and `result_docker` are absent.

### Relocation behavior and regeneration

The exported closure replaces every literal `/nix/store` byte sequence in
regular files and symlink targets with the selected runtime prefix. The exporter
validates the prefix and closure first, verifies the equal-byte-length
precondition, rejects an entry if any `/nix/store` literal remains, and records
the selected value in `portable/nix/runtime-prefix`.

A completed export with the same recorded prefix is updated incrementally. The
current `nix-store --query --requisites` output remains the inventory of record:
entries already present under the same Nix store basename are reused without a
recursive scan, copy, or rewrite. Each missing entry is copied under a temporary
name, rewritten and residual-checked there, made read-only, and only then renamed
to its final store basename. Existing exports made by earlier versions are
eligible for this reuse when their recorded prefix and relative result structure
show that export finalization completed. Reuse assumes generated entries under
`portable/nix` have not been modified since export; they are made read-only but
remain owned by the user. After manually changing or repairing generated
content, run with `--force`. Incremental mode deliberately does not recursively
verify reused entries.

After every required entry is ready, the exporter switches `portable/result` to
the current result; this switch is the incremental commit point. Failures before
that point, including an inability to enumerate the complete store, leave the
previously selected result usable and do not prune stale entries. After the
switch, final-name entries no longer in the closure are removed on a best-effort
basis and generated-directory write permissions are restored. A post-commit
cleanup or permission failure emits a warning and leaves the new result selected;
stale generated paths are retried by a later run. Temporary entries from a failed
or interrupted update are never reused and are removed by a later run. The
summary reports reused, copied, and removed store path counts.

A changed prefix or an incomplete prior export rebuilds the complete closure
because every relocated literal must agree. Use `--force` to request the same
complete rebuild deliberately even when the prefix is unchanged:

```bash
./utils/create_portable.sh --force
```

The exporter accepts no other arguments. Validation, copy, relocation, and
residual-reference failures do not save an environment prefix. Prefix-change and
forced rebuilds are prepared away from the active generated tree, so a failure
during preparation does not replace the previous successful export. During the
final tree/result switch, the prior successful tree remains in a temporary
backup: an ordinary failure restores it, while a later invocation either recovers
that proven successful backup from interrupted state or removes it after finding
an already successful active export. Failure to remove the old backup after the
new tree and result have committed is reported as a warning and does not turn the
completed export into a failure. Backup, temporary-path, and store enumerations
are captured and checked before their results are used for recovery or mutation.
At portable startup, the prefix recorded during export must be a symlink to this
checkout's absolute `portable/nix/store` path. The entrypoint reads and validates
the generated metadata; it does not select a new prefix from the current process
environment or current configuration. Missing or malformed metadata stops
startup before an alias is created or a shell is launched. The entrypoint creates
the recorded alias when absent and reuses it when already correct. If the path is
a different symlink, a regular file, or a directory, the entrypoint prints a
conflict and exits with status 73 without removing or replacing that object.
Resolve the conflict yourself before retrying.

The tracked `portable/entrypoint` wrappers and all other checkout files are left
alone. The generated paths, including the recorded prefix metadata, are ignored
by Git. Move the whole checkout as a unit; `portable/result` is relative, and the
recorded runtime alias is checked again at each portable startup.

The transformed closure is a runtime artifact only. Its store paths and content
hashes no longer describe the copied bytes, so do not use it for Nix builds,
substitution, signature verification, garbage collection, or other Nix store
operations. This mechanism has been validated for the project's current Linux
closure but is not a claim that every Nix package is relocatable.

## Customization

### Adding Packages

1. Copy the example package configuration to the repository root:
   ```bash
   cp example/packages.nix packages.nix
   ```

2. Edit `packages.nix` to add or remove packages:
   ```nix
   pkgs: with pkgs; [
     # Core utilities
     git      # Version control system
     ripgrep  # Fast text search tool
     fzf      # Command-line fuzzy finder

     # Uncomment or add packages you need
     # zsh       # Z Shell
     # neovim    # Vim-based text editor
     # nodejs    # Node.js runtime
   ]
   ```

3. Rebuild the environment:
   ```bash
   nix build
   ```

> Note: You must create `packages.nix` before running `nix build`. Copy from `example/packages.nix` and customize it. You can track your `packages.nix` in your own fork without causing merge conflicts when pulling upstream changes.

### Adding Configuration Files

To add your own configuration files:

1. Create the appropriate directory structure in the repository:
   ```bash
   mkdir -p config/app-name
   ```

2. Add your configuration files to this directory:
   ```bash
   # Example: Adding a Neovim configuration
   mkdir -p config/nvim
   touch config/nvim/init.lua

   # Example: Adding a Git configuration
   mkdir -p config/git
   touch config/git/config
   ```

3. Edit the configuration files with your preferred settings:
   ```bash
   # Example: Basic Neovim configuration
   echo 'vim.opt.number = true' > config/nvim/init.lua

   # Example: Basic Git configuration
   cat > config/git/config << EOF
   [user]
       name = Your Name
       email = your.email@example.com
   [core]
       editor = vim
   EOF
   ```

When you enter the environment using the shell-specific entrypoint scripts (`./entrypoint/bash`, `./entrypoint/zsh`, or `./entrypoint/fish`), these configuration files will be used automatically because the script sets the appropriate XDG environment variables to point to the directories within the repository.

### Finding Available Packages

To find available packages that you can add to your configuration:

1. **Search on the Nixpkgs website**:
   - Visit [search.nixos.org](https://search.nixos.org/packages) to search for packages
   - The package name shown in the search results is what you should add to your `packages.nix` file

2. **Search using the command line**:
   ```bash
   nix search nixpkgs package-name
   ```

3. **Browse the Nixpkgs repository**:
   - Visit the [Nixpkgs GitHub repository](https://github.com/NixOS/nixpkgs) to explore available packages
   - Packages are organized by category in the `pkgs` directory

## Directory Structure

```
shelffiles/
├── config/           # Configuration files
│   └── nix/          # Nix-related configuration
├── cache/            # XDG_CACHE_HOME
├── share/            # XDG_DATA_HOME
├── state/            # XDG_STATE_HOME
├── example/
│   └── packages.nix  # Example package definitions (template)
├── packages.nix      # User package definitions (copy from example/)
├── entrypoint/       # Shell-specific entrypoint scripts
│   ├── bash          # Bash entrypoint
│   ├── fish          # Fish entrypoint
│   └── zsh           # Zsh entrypoint
├── user_env.sh       # User-specific environment settings (git-ignored)
└── flake.nix         # Nix flake configuration
```

## Testing

To run tests for a specific shell:

```bash
# Test with zsh
./test/test.sh zsh

# Test with fish
./test/test.sh fish

# Test with bash
./test/test.sh bash
```

## How It Works

Shelffiles works by:

1. Setting XDG environment variables to point to directories within the repository
2. Using Nix flakes to manage packages in a reproducible way
3. Providing a consistent environment across different systems
4. Using a central package configuration file for easy customization

## Git Integration

### Devcontainer Configuration

The `example/git` directory contains Git filter settings for `devcontainer.json` files. This filter automatically excludes lines containing "shelffiles" when committing.

This allows you to add shelffiles-specific settings to your `devcontainer.json` for your local environment without sharing them in the repository.

To use this feature, copy the files in `example/git` to your Git configuration directory or reference them in your Git settings.

#### Example Usage

Here's an example of how you might customize your `devcontainer.json` with shelffiles-specific settings:

```json
{
  "name": "My Development Container",
  "image": "mcr.microsoft.com/devcontainers/base:ubuntu",

  // Standard settings (shared with everyone)
  "customizations": {
    "vscode": {
      "extensions": [
        "ms-python.python",
        "ms-vscode.cpptools"
      ]
    }
  },

  // Shelffiles-specific settings (will be filtered out when committing)
  "mounts": [
    "source=${localWorkspaceFolder}/shelffiles,target=/home/vscode/shelffiles,type=bind"
  ]
}
```
