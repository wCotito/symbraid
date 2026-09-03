# Optional watcher service recipes

These files are opt-in examples. The Symbraid installer never copies, enables,
starts, or registers either recipe.

## systemd user service

Create an environment file for one project, using the instance name from the
unit name:

    mkdir -p ~/.config/symbraid/projects
    printf '%s\n' 'SYMBRAID_PROJECT=/absolute/path/to/project' > ~/.config/symbraid/projects/demo.env

Copy systemd/symbraid-watch@.service to
~/.config/systemd/user/, then explicitly enable the instance:

    systemctl --user daemon-reload
    systemctl --user enable --now symbraid-watch@demo.service

To remove exactly that registration, stop and disable the same unit, then
remove only its environment file after checking the path:

    systemctl --user disable --now symbraid-watch@demo.service
    rm -- ~/.config/symbraid/projects/demo.env

## Windows user task

Run the registration script explicitly from a PowerShell session where the
user-scoped symbraid executable is on PATH:

    .\Register-SymbraidWatchTask.ps1 -Project C:\work\project

The script resolves the project directory and executable before registering a
limited, interactive user task. Use -Force only for an intentional
replacement. Remove the exact task explicitly:

    Unregister-ScheduledTask -TaskName 'Symbraid Watch' -Confirm:$false
