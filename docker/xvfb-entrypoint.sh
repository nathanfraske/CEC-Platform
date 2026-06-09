#!/bin/sh
# ----------------------------------------------------------------------------------------------
# Persistent-Xvfb entrypoint for the CEC routing container.
#
# Freerouting 1.7.0 is a Java/Swing GUI app: even headless it must construct AWT/Swing objects,
# so it needs (a) the FULL openjdk JRE (the -headless JRE omits libawt_xawt.so and hard-forces
# java.awt.headless=true -> HeadlessException) and (b) a real X display. We give it a persistent
# Xvfb on $DISPLAY started ONCE at container start, rather than per-invocation `xvfb-run -a`:
#   * cec_fr._fr_command() runs `java` DIRECTLY when $DISPLAY is set (skips xvfb-run), so the
#     whole route path uses this one server -- no per-run xvfb-run server-number races.
#   * the parallel Freerouting JVM swarm (one per seed/core) shares this single framebuffer fine.
#   * no defunct/zombie Xvfb pileup from a non-reaping PID 1 (compose also sets init: true / tini).
# `docker exec` into the running container inherits ENV DISPLAY and finds this live server.
# ----------------------------------------------------------------------------------------------
set -e

: "${DISPLAY:=:99}"
export DISPLAY

sock="/tmp/.X11-unix/X${DISPLAY#:}"
if [ ! -S "$sock" ]; then
    rm -f "/tmp/.X${DISPLAY#:}-lock" 2>/dev/null || true
    Xvfb "$DISPLAY" -screen 0 1280x1024x24 -nolisten tcp >/tmp/xvfb.log 2>&1 &
    # wait (up to ~10s) for the X socket so the first route doesn't race server startup
    i=0
    while [ ! -S "$sock" ] && [ "$i" -lt 100 ]; do
        i=$((i + 1))
        sleep 0.1
    done
    if [ ! -S "$sock" ]; then
        echo "xvfb-entrypoint: WARNING Xvfb did not come up on $DISPLAY; see /tmp/xvfb.log" >&2
        cat /tmp/xvfb.log >&2 2>/dev/null || true
    fi
fi

exec "$@"
