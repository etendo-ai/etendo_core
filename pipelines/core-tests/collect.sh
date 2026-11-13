#!/usr/bin/env bash
set -u
name="$1"
dest="results/$name"
mkdir -p "$dest"
[ -d build/test-results/test ] && cp -r build/test-results/test "$dest/xml" && rm -rf build/test-results/test
[ -d build/reports/tests/test ] && cp -r build/reports/tests/test "$dest/html" && rm -rf build/reports/tests/test
[ -d build/spock-reports ] && cp -r build/spock-reports "$dest/spock" && rm -rf build/spock-reports
[ -f build/jacoco/test.exec ] && mv build/jacoco/test.exec "$dest/jacoco-$name.exec"
exit 0
