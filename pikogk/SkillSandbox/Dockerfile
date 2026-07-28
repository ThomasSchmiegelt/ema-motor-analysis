# Sandbox for compiling + test-running LLM-generated PicoGK skill code.
# Build context is the pikogk/ repo root (see build command in README).
#
# Everything an LLM-generated skill needs is baked in at image-build time:
# .NET 9 SDK, the compiled PicoGK managed wrapper + native runtime, and a
# headless X server (Xvfb) with software OpenGL (llvmpipe) - PicoGK always
# opens a real GLFW/OpenGL window internally, verified to work fine against
# software rendering, no GPU passthrough needed.
#
# At container-run time (see SkillSandboxRunner.cs on the host), only a
# small per-request scratch directory is mounted in: the LLM-generated
# Generator.cs, a fixed Skill.csproj template, and params.json. The
# container itself runs with --network none and resource limits set by the
# host's `docker run` invocation - this Dockerfile does not set those, they
# are run-time flags.

# "-noble" = Ubuntu 24.04 base, matching the host that picogk.so was built
# on (glibc version compatibility - a plain Debian-based dotnet/sdk image
# has an older glibc that our native build's symbol versions don't satisfy).
FROM mcr.microsoft.com/dotnet/sdk:9.0-noble

RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb libgl1-mesa-dri libglx-mesa0 \
    && rm -rf /var/lib/apt/lists/*

# picogk.so's runtime deps, copied verbatim from the host build (Ubuntu
# 24.04) rather than apt-installed in this Debian-based image, to avoid any
# SONAME/version mismatch (e.g. Debian bookworm ships an older Boost than
# the 1.83.0 our native build linked against). libblosc is our own
# from-source build (see EXPERIENCE_REPORT.md #2) and isn't a distro
# package on either side, so it always has to be copied in like this.
COPY PicoGKRuntime/Dist/picogk.so /opt/picogk-native/picogk.so
COPY local-install/lib/libblosc.so.1.21.7 /usr/local/lib/libblosc.so.1
COPY SkillSandbox/host-libs/libtbb.so.12 /usr/local/lib/libtbb.so.12
COPY SkillSandbox/host-libs/libboost_iostreams.so.1.83.0 /usr/local/lib/libboost_iostreams.so.1.83.0
RUN ldconfig

WORKDIR /src
COPY PicoGK/ /src/PicoGK/
COPY SkillSandbox/Harness/ /src/Harness/

# Point PicoGK's compile-time-constant library path at the native runtime
# baked into this image (strPicoGKLib is a C# `const string`, so this must
# happen before compiling, not configured at container-run time).
RUN sed -i 's|^\([[:space:]]*\)public const string strPicoGKLib = ".*";|\1public const string strPicoGKLib = "/opt/picogk-native/picogk.so";|' \
    /src/PicoGK/Internals/Config.cs && \
    grep -n strPicoGKLib /src/PicoGK/Internals/Config.cs

# Bakes Harness.dll + PicoGK.dll + all transitive deps (SkiaSharp, ...) into
# one folder. Skill.csproj (built at container-run time) references
# /opt/harness/PicoGK.dll directly, so the assembly identity matches what
# Harness itself loads - required for the reflection-based invocation to work.
RUN dotnet publish /src/Harness/Harness.csproj -c Release -o /opt/harness

COPY SkillSandbox/entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

ENTRYPOINT ["/opt/entrypoint.sh"]
