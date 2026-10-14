// Hazz Wispr.app's main executable.
//
// Spawns `.venv/bin/python -m hazz_wispr` from the project folder as a *child*
// process (not exec), so macOS attributes Microphone / Accessibility / Input
// Monitoring permissions to Hazz Wispr.app instead of Terminal or Python.

#include <limits.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef PROJECT_DIR
#error "Build with -DPROJECT_DIR=\"/path/to/project\""
#endif

extern char **environ;
static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(void) {
    // .../Hazz Wispr.app/Contents/MacOS/HazzWispr -> .../Hazz Wispr.app
    char exe[PATH_MAX], app[PATH_MAX];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0 || !realpath(exe, app)) return 1;
    for (int i = 0; i < 3; i++) {
        char *slash = strrchr(app, '/');
        if (slash) *slash = '\0';
    }
    setenv("HAZZ_APP_PATH", app, 1);

    if (chdir(PROJECT_DIR) != 0) {
        perror("Hazz Wispr: project folder missing");
        return 1;
    }
    char python[PATH_MAX];
    snprintf(python, sizeof python, "%s/.venv/bin/python", PROJECT_DIR);
    char *argv[] = {python, "-m", "hazz_wispr", NULL};

    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);
    if (posix_spawn(&child, python, NULL, NULL, argv, environ) != 0) {
        perror("Hazz Wispr: could not start Python");
        return 1;
    }
    int status;
    while (waitpid(child, &status, 0) < 0) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
